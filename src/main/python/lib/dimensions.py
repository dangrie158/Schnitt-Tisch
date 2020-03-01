from typing import Union, TypeVar, Generic, Callable
from dataclasses import dataclass
import operator

T = TypeVar("T", float, int)


@dataclass
class Point(Generic[T]):
    x: T
    y: T

    def __getitem__(self, key):
        if key in (0, 1):
            return self.x if key == 0 else self.y
        else:
            raise IndexError()

    def __arithmetic_operation__(
        self, other: Union["Point", T], op: Callable[[T, T], T]
    ) -> "Point":
        if isinstance(other, Point):
            return Point(op(self.x, other.x), op(self.y, other.y))
        elif isinstance(other, (int, float)):
            return Point(op(self.x, other), op(self.y, other))
        else:
            raise TypeError(
                f"operation {op.__name__} only supported for operands of type {self.__class__.__name__}, int or float, not {type(other)}"
            )

    def __mul__(self, other):
        return self.__arithmetic_operation__(other, operator.mul)

    def __floordiv__(self, other):
        return self.__arithmetic_operation__(other, operator.floordiv)

    def __truediv__(self, other):
        return self.__arithmetic_operation__(other, operator.truediv)

    def __add__(self, other):
        return self.__arithmetic_operation__(other, operator.add)

    def __sub__(self, other):
        return self.__arithmetic_operation__(other, operator.sub)

    def as_integer(self):
        return Point(int(self.x), int(self.y))


Size = Point


def points_to_mm(size: float, dpi: int) -> float:
    """
    convert native units (points) to mm
    """
    return (size / dpi) * IN_TO_MM


def mm_to_points(size: float, dpi: int) -> float:
    """
    convert units MM to native units (points)
    """
    return (size / IN_TO_MM) * dpi


IN_TO_MM = 25.4


class Defaults:
    DPI = 72
    OVERLAP = 10
    FONT_SIZE = 25
    MARKER_SIZE = Size(35, 50)


PAGE_SIZES = {"A4": Size(210, 294), "A3": Size(294, 420), "A0": Size(841, 1189)}
