"""The part of a filter form that is about the rest of the changelist, not the filter."""

from __future__ import annotations

from django.contrib.admin.views.main import ERROR_FLAG, PAGE_VAR

#: Query parameters a sidebar form does not carry over. A new filter starts at page one,
#: and the changelist's error flag belongs to the request that set it.
DROPPED_PARAMS = frozenset({PAGE_VAR, ERROR_FLAG})


def carried_params(request, own):
    """Every query parameter except ``own``, as ``(name, value)`` pairs for hidden inputs.

    Submitting a filter from the sidebar is an ordinary GET, so anything the changelist is
    already doing - the search term, the ordering, the other filters - has to travel with
    it or it would be dropped. Repeated parameters stay repeated, one pair per value.
    """
    own = set(own)
    return [
        (name, value)
        for name, values in request.GET.lists()
        for value in values
        if name not in own and name not in DROPPED_PARAMS
    ]
