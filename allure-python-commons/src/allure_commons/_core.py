from __future__ import annotations

from typing import Any, Protocol

from pluggy import HookCaller, PluginManager
from allure_commons import _hooks

class _HookRelay(Protocol):
    # User hooks
    decorate_as_title: HookCaller
    add_title: HookCaller
    decorate_as_description: HookCaller
    add_description: HookCaller
    decorate_as_description_html: HookCaller
    add_description_html: HookCaller
    decorate_as_label: HookCaller
    add_label: HookCaller
    decorate_as_link: HookCaller
    add_link: HookCaller
    add_parameter: HookCaller
    start_step: HookCaller
    stop_step: HookCaller
    attach_data: HookCaller
    attach_file: HookCaller

    # Developer hooks
    start_fixture: HookCaller
    stop_fixture: HookCaller
    start_test: HookCaller
    stop_test: HookCaller
    report_result: HookCaller
    report_container: HookCaller
    report_attached_file: HookCaller
    report_attached_data: HookCaller


class MetaPluginManager(type):
    _plugin_manager: PluginManager | None = None

    @staticmethod
    def get_plugin_manager() -> PluginManager:
        if not MetaPluginManager._plugin_manager:
            MetaPluginManager._plugin_manager = PluginManager('allure')
            MetaPluginManager._plugin_manager.add_hookspecs(_hooks.AllureUserHooks)
            MetaPluginManager._plugin_manager.add_hookspecs(_hooks.AllureDeveloperHooks)

        return MetaPluginManager._plugin_manager

    def __getattr__(cls, attr: str) -> Any:
        pm = MetaPluginManager.get_plugin_manager()
        return getattr(pm, attr)


class plugin_manager(metaclass=MetaPluginManager):
    hook: _HookRelay
