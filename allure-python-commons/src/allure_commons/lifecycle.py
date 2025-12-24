from __future__ import annotations

from collections import OrderedDict
from contextlib import contextmanager
from typing import TYPE_CHECKING, TypeVar, overload, cast

from allure_commons._core import plugin_manager
from allure_commons.model2 import TestResultContainer
from allure_commons.model2 import TestResult
from allure_commons.model2 import Attachment, ATTACHMENT_PATTERN
from allure_commons.model2 import TestStepResult
from allure_commons.model2 import ExecutableItem
from allure_commons.model2 import TestBeforeResult
from allure_commons.model2 import TestAfterResult
from allure_commons.utils import uuid4
from allure_commons.utils import now
from allure_commons.types import AttachmentType

if TYPE_CHECKING:
    from collections.abc import Buffer, Generator

TItem = TypeVar('TItem', bound=ExecutableItem | TestResultContainer)


class AllureLifecycle:
    def __init__(self) -> None:
        self._items = OrderedDict()

    def _get_item(self, uuid: str | None = None, item_type: type[TItem] | None = None) -> TItem | None:
        uuid = uuid or self._last_item_uuid(item_type=item_type)
        return cast(TItem | None, self._items.get(uuid))

    def _pop_item(self, uuid: str | None = None, item_type: type[TItem] | None = None) -> TItem | None:
        uuid = uuid or self._last_item_uuid(item_type=item_type)
        return cast(TItem | None, self._items.pop(uuid, None))

    def _last_item_uuid(self, item_type: type[TItem] | None = None) -> str | None:
        for uuid in reversed(self._items):
            item = self._items.get(uuid)
            if item_type is None:
                return uuid
            elif isinstance(item, item_type):
                return uuid
        return None

    @contextmanager
    def schedule_test_case(self, uuid: str | None = None) -> Generator[TestResult, None, None]:
        test_result = TestResult()
        test_result.uuid = uuid or uuid4()
        self._items[test_result.uuid] = test_result
        yield test_result

    @contextmanager
    def update_test_case(self, uuid: str | None = None) -> Generator[TestResult | None, None, None]:
        yield self._get_item(uuid=uuid, item_type=TestResult)

    def write_test_case(self, uuid: str | None = None) -> None:
        test_result: TestResult | None = self._pop_item(uuid=uuid, item_type=TestResult)
        if test_result:
            plugin_manager.hook.report_result(result=test_result)

    @contextmanager
    def start_step(self, parent_uuid: str | None = None, uuid: str | None = None) -> Generator[TestStepResult, None, None]:
        parent: ExecutableItem | None = self._get_item(uuid=parent_uuid, item_type=ExecutableItem)
        step = TestStepResult()
        step.start = now()
        parent.steps.append(step)  # ty:ignore[possibly-missing-attribute]
        self._items[uuid or uuid4()] = step
        yield step

    @contextmanager
    def update_step(self, uuid: str | None = None) -> Generator[TestStepResult | None, None, None]:
        yield self._get_item(uuid=uuid, item_type=TestStepResult)

    def stop_step(self, uuid: str | None = None) -> None:
        step: TestStepResult | None = self._pop_item(uuid=uuid, item_type=TestStepResult)
        if step and not step.stop:
            step.stop = now()

    @contextmanager
    def start_container(self, uuid: str | None = None) -> Generator[TestResultContainer | None, None, None]:
        container: TestResultContainer = TestResultContainer(uuid=uuid or uuid4())
        self._items[container.uuid] = container
        yield container

    def containers(self) -> Generator[TestResultContainer, None, None]:
        for item in self._items.values():
            if isinstance(item, TestResultContainer):
                yield item

    @contextmanager
    def update_container(self, uuid: str | None = None) -> Generator[TestResultContainer | None, None, None]:
        yield self._get_item(uuid=uuid, item_type=TestResultContainer)

    def write_container(self, uuid: str | None = None) -> None:
        container: TestResultContainer | None = self._pop_item(uuid=uuid, item_type=TestResultContainer)
        if container and (container.befores or container.afters):
            plugin_manager.hook.report_container(container=container)

    @contextmanager
    def start_before_fixture(self, parent_uuid: str | None = None, uuid: str | None = None) -> Generator[TestBeforeResult, None, None]:
        fixture = TestBeforeResult()
        parent: TestResultContainer | None = self._get_item(uuid=parent_uuid, item_type=TestResultContainer)
        if parent:
            parent.befores.append(fixture)
        self._items[uuid or uuid4()] = fixture
        yield fixture

    @contextmanager
    def update_before_fixture(self, uuid: str | None = None) -> Generator[TestBeforeResult | None, None, None]:
        yield self._get_item(uuid=uuid, item_type=TestBeforeResult)

    def stop_before_fixture(self, uuid: str | None = None) -> None:
        fixture: TestBeforeResult | None = self._pop_item(uuid=uuid, item_type=TestBeforeResult)
        if fixture and not fixture.stop:
            fixture.stop = now()

    @contextmanager
    def start_after_fixture(self, parent_uuid: str | None = None, uuid: str | None = None) -> Generator[TestAfterResult, None, None]:
        fixture = TestAfterResult()
        parent: TestResultContainer | None = self._get_item(uuid=parent_uuid, item_type=TestResultContainer)
        if parent:
            parent.afters.append(fixture)
        self._items[uuid or uuid4()] = fixture
        yield fixture

    @contextmanager
    def update_after_fixture(self, uuid: str | None = None) -> Generator[TestAfterResult | None, None, None]:
        yield self._get_item(uuid=uuid, item_type=TestAfterResult)

    def stop_after_fixture(self, uuid: str | None = None) -> None:
        fixture: TestAfterResult | None = self._pop_item(uuid=uuid, item_type=TestAfterResult)
        if fixture and not fixture.stop:
            fixture.stop = now()

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
        last_uuid = parent_uuid if parent_uuid else self._last_item_uuid(ExecutableItem)
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
