class UnregisteredStrategyError(Exception):
    """No render strategy is registered for a junction's ``strategy_tier``.

    Milestone A registers tier 3 only; tiers 2/4/5 raise this rather than
    silently substituting a wrong-sounding fallback (spec §4). The message lists
    the tiers that *are* registered.
    """
