from typing import List, Tuple

import math

import itertools


class Pagination:
    """
    Paginator for arbitrary lists of objects.

    :param records: Records to paginate.
    :param page_size: Number of records per page.
    :param align_end: If True, aligns the records to fill up the last page. Useful e.g. for
        displaying chronological data but starting from the most recent records on the last page.
        If False, aligns the records to fill up the first page.
    """
    def __init__(self, records: List, page_size: int, align_end=False):
        self.records = list(records)

        self.page_size = page_size
        self.align_end = align_end
        self._current_page = 0 if not align_end else self.total_pages - 1

    @property
    def total_pages(self):
        """ Calculate the total pages. """
        return int(math.ceil(len(self.records) / self.page_size))

    @property
    def page(self) -> int:
        return self._current_page

    @page.setter
    def page(self, page: int):
        if page < 0 or page >= self.total_pages:
            raise IndexError(page)
        self._current_page = page

    def get_page_records(self) -> List:
        """ Get the records for the current page. """
        start_index, end_index = self.get_page_indices()
        return self.records[start_index:end_index]

    def get_page_indices(self) -> Tuple[int, int]:
        """ Get the indices for the current page. """
        if not self.align_end:
            start = self.page * self.page_size
            end = start + self.page_size
        else:
            end = len(self.records) - (self.total_pages - self.page - 1) * self.page_size
            start = max(0, end - self.page_size)
        return start, end

    def __len__(self):
        return len(self.records)

    def __iter__(self):
        start_index, end_index = self.get_page_indices()
        return itertools.islice(self.records, start_index, end_index)
