from django.db import transaction


class OuterTransactionMiddleware:
    """What a project's own middleware might do: hold the whole request in a transaction."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        with transaction.atomic():
            return self.get_response(request)
