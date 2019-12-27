# Copyright 2019 Apex.AI, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Module for memory usage events processing."""

from typing import Dict

from tracetools_read import get_field

from . import EventHandler
from . import EventMetadata
from ..data_model.memory_usage import MemoryUsageDataModel


class MemoryUsageHandler(EventHandler):
    """
    Handler that extracts data for memory usage.

    It uses the following events:
        * lttng_ust_libc:malloc
        * lttng_ust_libc:calloc
        * lttng_ust_libc:realloc
        * lttng_ust_libc:free
        * lttng_ust_libc:memalign
        * lttng_ust_libc:posix_memalign

    The above events are generated when LD_PRELOAD-ing liblttng-ust-libc-wrapper.so, see:
    https://lttng.org/docs/v2.10/#doc-liblttng-ust-libc-pthread-wrapper

    Implementation inspired by Trace Compass' implementation:
    https://git.eclipse.org/c/tracecompass/org.eclipse.tracecompass.git/tree/lttng/org.eclipse.tracecompass.lttng2.ust.core/src/org/eclipse/tracecompass/internal/lttng2/ust/core/analysis/memory/UstMemoryStateProvider.java#n161
    """

    def __init__(
        self,
        **kwargs,
    ) -> None:
        # Link event to handling method
        handler_map = {
            'lttng_ust_libc:malloc':
                self._handle_malloc,
            'lttng_ust_libc:calloc':
                self._handle_calloc,
            'lttng_ust_libc:realloc':
                self._handle_realloc,
            'lttng_ust_libc:free':
                self._handle_free,
            'lttng_ust_libc:memalign':
                self._handle_memalign,
            'lttng_ust_libc:posix_memalign':
                self._handle_posix_memalign,
        }
        super().__init__(
            handler_map=handler_map,
            **kwargs,
        )

        self._data_model = MemoryUsageDataModel()

        # Temporary buffers
        # pointer -> current memory size
        # (used to know keep track of the memory size allocated at a given pointer)
        self._memory: Dict[int, int] = {}

    @property
    def data(self) -> MemoryUsageDataModel:
        return self._data_model

    def _handle_malloc(
        self, event: Dict, metadata: EventMetadata
    ) -> None:
        ptr = get_field(event, 'ptr')
        if ptr != 0:
            size = get_field(event, 'size')
            self._handle(event, metadata, ptr, size)

    def _handle_calloc(
        self, event: Dict, metadata: EventMetadata
    ) -> None:
        ptr = get_field(event, 'ptr')
        if ptr != 0:
            nmemb = get_field(event, 'nmemb')
            size = get_field(event, 'size')
            self._handle(event, metadata, ptr, size * nmemb)

    def _handle_realloc(
        self, event: Dict, metadata: EventMetadata
    ) -> None:
        ptr = get_field(event, 'ptr')
        if ptr != 0:
            new_ptr = get_field(event, 'in_ptr')
            size = get_field(event, 'size')
            self._handle(event, metadata, ptr, 0)
            self._handle(event, metadata, new_ptr, size)

    def _handle_free(
        self, event: Dict, metadata: EventMetadata
    ) -> None:
        ptr = get_field(event, 'ptr')
        if ptr != 0:
            self._handle(event, metadata, ptr, 0)

    def _handle_memalign(
        self, event: Dict, metadata: EventMetadata
    ) -> None:
        ptr = get_field(event, 'ptr')
        if ptr != 0:
            size = get_field(event, 'size')
            self._handle(event, metadata, ptr, size)

    def _handle_posix_memalign(
        self, event: Dict, metadata: EventMetadata
    ) -> None:
        ptr = get_field(event, 'out_ptr')
        if ptr != 0:
            size = get_field(event, 'size')
            self._handle(event, metadata, ptr, size)

    def _handle(
        self,
        event: Dict,
        metadata: EventMetadata,
        ptr: int,
        size: int,
    ) -> None:
        timestamp = metadata.timestamp
        tid = metadata.tid

        memory_difference = size
        # Store the size allocated for the given pointer
        if memory_difference != 0:
            self._memory[ptr] = memory_difference
        else:
            # Othersize, if size is 0, it means it was deleted
            # Try to fetch the size stored previously
            allocated_memory = self._memory.get(ptr, None)
            if allocated_memory is not None:
                memory_difference = -allocated_memory

        # Add to data model
        self.data.add_memory_difference(timestamp, tid, memory_difference)
