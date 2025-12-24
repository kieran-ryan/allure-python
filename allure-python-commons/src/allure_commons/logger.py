from __future__ import annotations

import io
import os
from pathlib import Path
import json
import uuid
import shutil
from typing import Any, TYPE_CHECKING

from attr import asdict
from allure_commons import hookimpl

if TYPE_CHECKING:
    from collections.abc import Buffer

    from allure_commons.model2 import TestResult, TestResultContainer

INDENT = 4


class AllureFileLogger:

    def __init__(self, report_dir: str | Path, clean: bool = False) -> None:
        self._report_dir = Path(report_dir).absolute()
        if self._report_dir.is_dir() and clean:
            shutil.rmtree(self._report_dir, ignore_errors=True)
        self._report_dir.mkdir(parents=True, exist_ok=True)

    def _report_item(self, item: TestResult | TestResultContainer) -> None:
        indent = INDENT if os.environ.get("ALLURE_INDENT_OUTPUT") else None
        filename = item.file_pattern.format(prefix=uuid.uuid4())
        data = asdict(item, filter=lambda _, v: v or v is False)
        with io.open(self._report_dir / filename, 'w', encoding='utf8') as json_file:
            json.dump(data, json_file, indent=indent, ensure_ascii=False)

    @hookimpl
    def report_result(self, result: TestResult) -> None:
        self._report_item(result)

    @hookimpl
    def report_container(self, container: TestResultContainer) -> None:
        self._report_item(container)

    @hookimpl
    def report_attached_file(self, source: str, file_name: str) -> None:
        destination = self._report_dir / file_name
        shutil.copy2(source, destination)

    @hookimpl
    def report_attached_data(self, body: Buffer | str, file_name: str) -> None:
        destination = self._report_dir / file_name
        with open(destination, 'wb') as attached_file:
            if isinstance(body, str):
                attached_file.write(body.encode('utf-8'))
            else:
                attached_file.write(body)


class AllureMemoryLogger:

    def __init__(self) -> None:
        self.test_cases: list[dict[str, Any]] = []
        self.test_containers: list[dict[str, Any]] = []
        self.attachments: dict[str, Buffer | str] = {}

    @hookimpl
    def report_result(self, result: TestResult) -> None:
        data = asdict(result, filter=lambda _, v: v or v is False)
        self.test_cases.append(data)

    @hookimpl
    def report_container(self, container: TestResultContainer) -> None:
        data = asdict(container, filter=lambda _, v: v or v is False)
        self.test_containers.append(data)

    @hookimpl
    def report_attached_file(self, source: str, file_name: str) -> None:
        self.attachments[file_name] = source

    @hookimpl
    def report_attached_data(self, body: Buffer | str, file_name: str) -> None:
        self.attachments[file_name] = body
