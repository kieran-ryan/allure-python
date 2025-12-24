from __future__ import annotations

import threading
from collections import OrderedDict, defaultdict
from typing import TYPE_CHECKING, Any

from allure_commons._core import plugin_manager
from allure_commons.model2 import (
    ATTACHMENT_PATTERN,
    Attachment,
    ExecutableItem,
    TestAfterResult,
    TestBeforeResult,
    TestResult,
    TestResultContainer,
    TestStepResult,
)
from allure_commons.types import AttachmentType
from allure_commons.utils import now

if TYPE_CHECKING:
    from collections.abc import Buffer


class ThreadContextItems:

    _thread_context = defaultdict(OrderedDict)
    _init_thread: threading.Thread

    @property
    def thread_context(self) -> OrderedDict[Any, Any]:
        context = self._thread_context[threading.current_thread()]
        if not context and threading.current_thread() is not self._init_thread:
            uuid, last_item = next(reversed(self._thread_context[self._init_thread].items()))
            context[uuid] = last_item
        return context

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self._init_thread = threading.current_thread()
        super().__init__(*args, **kwargs)

    def __setitem__(self, key: Any, value: Any) -> None:
        self.thread_context.__setitem__(key, value)

    def __getitem__(self, item: Any) -> Any:
        return self.thread_context.__getitem__(item)

    def __iter__(self) -> Any:
        return self.thread_context.__iter__()

    def __reversed__(self) -> Any:
        return self.thread_context.__reversed__()

    def get(self, key: Any) -> Any:
        return self.thread_context.get(key)

    def pop(self, key: Any) -> Any:
        return self.thread_context.pop(key)

    def cleanup(self) -> None:
        stopped_threads = []
        for thread in self._thread_context.keys():
            if not thread.is_alive():
                stopped_threads.append(thread)
        for thread in stopped_threads:
            del self._thread_context[thread]


class AllureReporter:
    def __init__(self) -> None:
        self._items = ThreadContextItems()
        self._orphan_items: list[str] = []

    def _update_item(self, uuid: str | None = None, **kwargs: Any) -> None:
        item = self._items[uuid] if uuid else self._items[next(reversed(self._items))]
        for name, value in kwargs.items():
            attr = getattr(item, name)
            if isinstance(attr, list):
                attr.append(value)
            else:
                setattr(item, name, value)

    def _last_executable(self) -> str | None:
        for _uuid in reversed(self._items):
            if isinstance(self._items[_uuid], ExecutableItem):
                return _uuid
        return None

    def get_item(self, uuid: str) -> Any | None:
        return self._items.get(uuid)

    def get_last_item(self, item_type: Any | None = None) -> Any:
        for _uuid in reversed(self._items):
            if item_type is None:
                return self._items.get(_uuid)
            if isinstance(self._items[_uuid], item_type):
                return self._items.get(_uuid)

    def start_group(self, uuid: str, group: TestResultContainer) -> None:
        self._items[uuid] = group

    def stop_group(self, uuid: str, **kwargs: Any) -> None:
        self._update_item(uuid, **kwargs)
        group = self._items.pop(uuid)
        plugin_manager.hook.report_container(container=group)

    def update_group(self, uuid: str, **kwargs: Any) -> None:
        self._update_item(uuid, **kwargs)

    def start_before_fixture(self, parent_uuid: str, uuid: str, fixture: TestBeforeResult) -> None:
        self._items.get(parent_uuid).befores.append(fixture)
        self._items[uuid] = fixture

    def stop_before_fixture(self, uuid: str, **kwargs: Any) -> None:
        self._update_item(uuid, **kwargs)
        self._items.pop(uuid)

    def start_after_fixture(self, parent_uuid: str, uuid: str, fixture: TestAfterResult) -> None:
        self._items.get(parent_uuid).afters.append(fixture)
        self._items[uuid] = fixture

    def stop_after_fixture(self, uuid: str, **kwargs: Any) -> None:
        self._update_item(uuid, **kwargs)
        fixture = self._items.pop(uuid)
        fixture.stop = now()

    def schedule_test(self, uuid: str, test_case: TestResult) -> None:
        self._items[uuid] = test_case

    def get_test(self, uuid: str | None = None) -> Any | TestResult:
        return self.get_item(uuid) if uuid else self.get_last_item(TestResult)

    def close_test(self, uuid: str) -> None:
        test_case = self._items.pop(uuid)
        self._items.cleanup()
        plugin_manager.hook.report_result(result=test_case)

    def drop_test(self, uuid: str) -> None:
        self._items.pop(uuid)

    def start_step(self, parent_uuid: str | None, uuid: str, step: TestStepResult) -> None:
        parent_uuid = parent_uuid if parent_uuid else self._last_executable()
        if parent_uuid is None:
            self._orphan_items.append(uuid)
        else:
            self._items[parent_uuid].steps.append(step)
            self._items[uuid] = step

    def stop_step(self, uuid: str, **kwargs: Any) -> None:
        if uuid in self._orphan_items:
            self._orphan_items.remove(uuid)
        else:
            self._update_item(uuid, **kwargs)
            self._items.pop(uuid)

    def _attach(
        self,
        uuid: str,
        name: str,
        attachment_type: AttachmentType | str | None = None,
        extension: str | None = None,
        parent_uuid: str | None = None,
    ) -> str:
        mime_type = attachment_type
        extension = extension if extension else 'attach'

        if type(attachment_type) is AttachmentType:
            extension = attachment_type.extension
            mime_type = attachment_type.mime_type

        file_name = ATTACHMENT_PATTERN.format(prefix=uuid, ext=extension)
        attachment = Attachment(source=file_name, name=name, type=mime_type)
        last_uuid = parent_uuid if parent_uuid else self._last_executable()
        self._items[last_uuid].attachments.append(attachment)

        return file_name

    def attach_file(
        self,
        uuid: str,
        source: str,
        name: str,
        attachment_type: AttachmentType | None = None,
        extension: str | None = None,
        parent_uuid: str | None = None,
    ) -> None:
        file_name = self._attach(uuid, name=name, attachment_type=attachment_type,
                                 extension=extension, parent_uuid=parent_uuid)
        plugin_manager.hook.report_attached_file(source=source, file_name=file_name)

    def attach_data(
        self,
        uuid: str,
        body: Buffer | str,
        name: str,
        attachment_type: AttachmentType | None = None,
        extension: str | None = None,
        parent_uuid: str | None = None,
    ) -> None:
        file_name = self._attach(uuid, name=name, attachment_type=attachment_type,
                                 extension=extension, parent_uuid=parent_uuid)
        plugin_manager.hook.report_attached_data(body=body, file_name=file_name)
