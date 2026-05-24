from contextlib import suppress

from rest_framework.pagination import PageNumberPagination


class StandardResultsSetPagination(PageNumberPagination):
    page_query_param = "page"
    page_size = 20
    page_size_query_param = "page_size"
    limit_query_param = "limit"
    max_page_size = 100

    def get_page_size(self, request):
        if self.page_size_query_param in request.query_params:
            return super().get_page_size(request)

        limit = request.query_params.get(self.limit_query_param)

        if limit not in (None, ""):
            with suppress(TypeError, ValueError):
                parsed_limit = int(limit)

                if parsed_limit > 0:
                    if self.max_page_size is not None:
                        return min(parsed_limit, self.max_page_size)

                    return parsed_limit

        return super().get_page_size(request)