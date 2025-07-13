import os

COLOR_HEXS = [
    "#41EBAE",
    "#708AF5",
    "#BC70F6",
    "#F66FBE",
    "#E65825",
    "#F99E44",
    "#EDBD20",
]
COLOR_NAMES = [
    "Green",  # "#41EBAE"
    "Blue",  # "#708AF5"
    "Purple",  # "#BC70F6"
    "Pink",  # "#F66FBE"
    "Red",  # "#E65825"
    "Orange",  # "#F99E44"
    "Yellow",  # "#EDBD20"
]


class Color:
    """
    Represents a the color the user chose.
    Attributes:
        color_index (int): the index from the list of color options.
    """

    def __init__(self, color_index):
        self.color_index = color_index
        self.color_name = COLOR_NAMES[color_index]
