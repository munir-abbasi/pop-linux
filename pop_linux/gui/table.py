"""Publication presentation model; sorting/filtering never mutate the dataset."""
from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt

from pop_linux.models import Paper

COLUMNS = (
    ("Publication title", "title"), ("Authors", "author_string"),
    ("Year", "year"), ("Journal / source", "journal"), ("Citations", "citations"),
    ("Provider", "source_provider"), ("DOI", "doi"), ("URL", "url"),
)


class PublicationModel(QAbstractTableModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.papers: list[Paper] = []

    def set_papers(self, papers: list[Paper]):
        self.beginResetModel()
        self.papers = list(papers)
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.papers)

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(COLUMNS)

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return COLUMNS[section][0]
        return super().headerData(section, orientation, role)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        value = getattr(self.papers[index.row()], COLUMNS[index.column()][1])
        if role == Qt.ItemDataRole.UserRole:
            if index.column() in (2, 4):
                return value if value is not None else -1
            return str(value or "").casefold()
        if role in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.ToolTipRole):
            return str(value) if value is not None and value != "" else "—"
        if role == Qt.ItemDataRole.TextAlignmentRole and index.column() in (2, 4):
            return int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        return None
