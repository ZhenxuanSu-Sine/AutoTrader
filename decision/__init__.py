"""Decision package.

This package holds all trading strategies.  Each strategy should
inherit from :class:`backtrader.Strategy` (or a subclass) and be
registered in ``evaluation/evaluate.py`` via the ``load_strategy``
function.
"""