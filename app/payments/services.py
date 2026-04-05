"""Payment services — DEPRECATED legacy wrapper.

.. deprecated::
    All functions have been moved to ``app.payments.use_case.*`` modules.
    Import from the new locations instead.  Every access through this module
    emits a ``DeprecationWarning`` (PEP 562).

Migration map
─────────────
get_user_credits              → app.payments.use_case.credits
has_credits_available         → app.payments.use_case.credits
consume_credit                → app.payments.use_case.credits
create_preference             → app.payments.use_case.preferences
create_credit_package_preference → app.payments.use_case.preferences
process_webhook               → app.payments.use_case.webhook.processor
sync_payment_status_from_mp    → app.payments.use_case.webhook.status_syncer
_verify_webhook_signature     → app.payments.use_case.client
_add_credits_to_user          → app.payments.use_case.webhook.credit_manager
"""

from __future__ import annotations

import warnings

# ── lazy-loaded symbol cache (PEP 562) ─────────────────────────

_MODULES: dict[str, str] = {
    "get_user_credits": "app.payments.use_case.credits",
    "has_credits_available": "app.payments.use_case.credits",
    "consume_credit": "app.payments.use_case.credits",
    "create_preference": "app.payments.use_case.preferences",
    "create_credit_package_preference": "app.payments.use_case.preferences",
    "process_webhook": "app.payments.use_case.webhook.processor",
    "_sync_payment_status_from_mp": "app.payments.use_case.webhook.status_syncer",
    "_verify_webhook_signature": "app.payments.use_case.client",
    "_get_mp_client": "app.payments.use_case.client",
    "_add_credits_to_user": "app.payments.use_case.webhook.credit_manager",
}

_CACHE: dict[str, object] = {}


def __getattr__(name: str):
    if name not in _MODULES:
        raise AttributeError(
            f"module 'app.payments.services' has no attribute '{name}'"
        )

    if name not in _CACHE:
        module_path = _MODULES[name]
        # Parse module_path to get the short name for the warning message
        short_module = module_path.split(".")[-1]
        warnings.warn(
            f"Importing '{name}' from 'app.payments.services' is deprecated. "
            f"Use '{module_path}.{name}' instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        import importlib
        mod = importlib.import_module(module_path)
        _CACHE[name] = getattr(mod, name)

    return _CACHE[name]


def __dir__():
    return list(_MODULES.keys())
