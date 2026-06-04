"""Tests for ClientCapabilities parsing and accessor methods."""

from pymcp.capabilities.registry import ClientCapabilities


class TestRoots:
    def test_supports_roots_when_declared(self):
        cc = ClientCapabilities({"roots": {"listChanged": True}})
        assert cc.supports_roots()

    def test_supports_roots_empty_dict(self):
        cc = ClientCapabilities({"roots": {}})
        assert cc.supports_roots()

    def test_roots_not_supported_when_absent(self):
        cc = ClientCapabilities({})
        assert not cc.supports_roots()

    def test_supports_roots_list_changed(self):
        cc = ClientCapabilities({"roots": {"listChanged": True}})
        assert cc.supports_roots_list_changed()

    def test_roots_list_changed_false(self):
        cc = ClientCapabilities({"roots": {}})
        assert not cc.supports_roots_list_changed()


class TestSampling:
    def test_supports_sampling_when_declared(self):
        cc = ClientCapabilities({"sampling": {}})
        assert cc.supports_sampling()

    def test_sampling_not_supported_when_absent(self):
        cc = ClientCapabilities({})
        assert not cc.supports_sampling()

    def test_supports_sampling_tools(self):
        cc = ClientCapabilities({"sampling": {"tools": {}}})
        assert cc.supports_sampling_tools()

    def test_sampling_tools_not_supported(self):
        cc = ClientCapabilities({"sampling": {}})
        assert not cc.supports_sampling_tools()


class TestElicitation:
    def test_supports_elicitation_any_mode(self):
        cc = ClientCapabilities({"elicitation": {"form": {}, "url": {}}})
        assert cc.supports_elicitation()

    def test_supports_elicitation_form(self):
        cc = ClientCapabilities({"elicitation": {"form": {}}})
        assert cc.supports_elicitation("form")
        assert not cc.supports_elicitation("url")

    def test_supports_elicitation_url(self):
        cc = ClientCapabilities({"elicitation": {"url": {}}})
        assert cc.supports_elicitation("url")
        assert not cc.supports_elicitation("form")

    def test_empty_elicitation_means_form(self):
        """Per spec, empty elicitation {} == form-only."""
        cc = ClientCapabilities({"elicitation": {}})
        assert cc.supports_elicitation("form")
        assert not cc.supports_elicitation("url")

    def test_elicitation_not_supported_when_absent(self):
        cc = ClientCapabilities({})
        assert not cc.supports_elicitation()
        assert not cc.supports_elicitation("form")


class TestClientTasks:
    def test_supports_client_tasks(self):
        cc = ClientCapabilities({"tasks": {"requests": {"elicitation": {"create": {}}}}})
        assert cc.supports_client_tasks()

    def test_client_tasks_not_supported(self):
        cc = ClientCapabilities({})
        assert not cc.supports_client_tasks()

    def test_supports_task_request(self):
        cc = ClientCapabilities({
            "tasks": {
                "requests": {
                    "elicitation": {"create": {}},
                    "sampling": {"createMessage": {}},
                }
            }
        })
        assert cc.supports_task_request("elicitation", "create")
        assert cc.supports_task_request("sampling", "createMessage")
        assert not cc.supports_task_request("elicitation", "nonexistent")
        assert not cc.supports_task_request("nonexistent", "create")


class TestExperimental:
    def test_supports_experimental(self):
        cc = ClientCapabilities({"experimental": {"myFeature": {}}})
        assert cc.supports_experimental("myFeature")

    def test_experimental_not_supported(self):
        cc = ClientCapabilities({})
        assert not cc.supports_experimental("myFeature")

    def test_specific_experimental_absent(self):
        cc = ClientCapabilities({"experimental": {"otherFeature": {}}})
        assert not cc.supports_experimental("myFeature")


class TestGenericSupports:
    def test_supports_tasks_requires_explicit(self):
        cc = ClientCapabilities({})
        assert not cc.supports("tasks")

    def test_supports_tasks_when_present(self):
        cc = ClientCapabilities({"tasks": {}})
        assert cc.supports("tasks")

    def test_supports_arbitrary_feature_when_present(self):
        cc = ClientCapabilities({"roots": {}})
        assert cc.supports("roots")

    def test_feature_not_supported_when_absent(self):
        cc = ClientCapabilities({})
        assert not cc.supports("roots")
