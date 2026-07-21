"""Change class definitions for CI impact analysis."""

from __future__ import annotations

from enum import Enum


class ChangeClass(str, Enum):
    PRODUCT = "product"
    TEST = "test"
    BUILD = "build"
    TOOLCHAIN = "toolchain"
    PACKAGE_DATA = "package_data"
    VALIDATOR = "validator"
    DOCUMENTATION = "documentation"
    AGENT_WORKFLOW = "agent_workflow"
    REPOSITORY_METADATA = "repository_metadata"
    UNKNOWN = "unknown"


FULL_CI_CHANGE_CLASSES = frozenset(
    {
        ChangeClass.PRODUCT,
        ChangeClass.TEST,
        ChangeClass.BUILD,
        ChangeClass.TOOLCHAIN,
        ChangeClass.PACKAGE_DATA,
        ChangeClass.UNKNOWN,
    }
)

LIGHTWEIGHT_CHANGE_CLASSES = frozenset(
    {
        ChangeClass.DOCUMENTATION,
        ChangeClass.AGENT_WORKFLOW,
        ChangeClass.REPOSITORY_METADATA,
        ChangeClass.VALIDATOR,
    }
)

NON_CI_CHANGE_CLASSES = frozenset(
    {
        ChangeClass.DOCUMENTATION,
        ChangeClass.AGENT_WORKFLOW,
        ChangeClass.REPOSITORY_METADATA,
    }
)

CLASS_SECTION_KEYS = {
    ChangeClass.PRODUCT: "product",
    ChangeClass.TEST: "tests",
    ChangeClass.BUILD: "build",
    ChangeClass.TOOLCHAIN: "toolchain",
    ChangeClass.PACKAGE_DATA: "packageData",
    ChangeClass.VALIDATOR: "validators",
    ChangeClass.DOCUMENTATION: "documentation",
    ChangeClass.AGENT_WORKFLOW: "agentWorkflow",
    ChangeClass.REPOSITORY_METADATA: "repositoryMetadata",
}

CLASS_PRIORITY: tuple[ChangeClass, ...] = (
    ChangeClass.TOOLCHAIN,
    ChangeClass.BUILD,
    ChangeClass.TEST,
    ChangeClass.PRODUCT,
    ChangeClass.PACKAGE_DATA,
    ChangeClass.VALIDATOR,
    ChangeClass.DOCUMENTATION,
    ChangeClass.AGENT_WORKFLOW,
    ChangeClass.REPOSITORY_METADATA,
)
