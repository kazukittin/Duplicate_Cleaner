from dataclasses import dataclass, field
from typing import Optional

@dataclass
class ResultItem:
    path: str
    size: int
    width: int
    height: int
    mtime: Optional[float] = None
    sha256: Optional[str] = None
    phash: Optional[str] = None
    noise: Optional[float] = None
    similarity: Optional[int] = None
    noise_score: Optional[int] = None

    @property
    def pixels(self) -> int:
        return (self.width or 0) * (self.height or 0)

@dataclass
class ResultGroup:
    kind: str  # "重複" or "類似" など
    title: str
    items: list[ResultItem] = field(default_factory=list)
    score: Optional[float] = None
