"""
UserView.__init__ registered its retranslate_ui as a language-change
callback and unregistered it via
`self.destroyed.connect(lambda: unregister_language_callback(self.retranslate_ui))`.
That lambda closes over `self`, creating a reference cycle (self -> Qt's
internal connection list for the `destroyed` signal -> the lambda -> self)
that only the cyclic garbage collector can break -- plain refcounting can
never drop it to zero.

In a long-running process that constructs and discards many views (the
full pytest suite is one; a POS terminal left open for a full shift doing
repeated navigation is another), eventually a full `gc.collect()` pass has
to unwind a big tangle of these cycles. When that happens to finalize a
QObject whose C++ side is already mid-teardown before Python's GC gets to
the lambda, calling back into `self.retranslate_ui` reads through a
half-destroyed object -- reproduced as a hard segfault (not a catchable
RuntimeError) via 20x construct-and-discard + gc.collect() in an isolated
script. Wrapping `self` in a weakref inside the lambda avoids creating the
cycle at all, so the view is reclaimed by ordinary refcounting the moment
its last strong reference drops, and a full GC pass never needs to touch
it.
"""

import gc

import pytest

from cbpos.ui.views.user_view import UserView

pytestmark = pytest.mark.usefixtures("qapp")


class TestNoReferenceCycleOnDestroy:
    def test_view_is_reclaimed_by_refcounting_alone_without_a_gc_pass(self, db_session):
        gc.disable()
        try:
            view = UserView()
            still_alive = []
            view.destroyed.connect(lambda: still_alive.append(False))
            del view
            # If refcounting alone couldn't reclaim it, the object -- and
            # its destroyed-signal connections -- would only go away once
            # a cyclic gc.collect() runs, which we've deliberately disabled.
            assert still_alive == [False]
        finally:
            gc.enable()
