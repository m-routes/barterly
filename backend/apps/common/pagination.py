from rest_framework.pagination import PageNumberPagination


class DefaultPagination(PageNumberPagination):
    """?page=N&page_size=M, 20 per page by default, at most 100.

    Response: {"count", "next", "previous", "results"}.
    """

    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100
