from typing import Any, Dict, List, Union

import parsy

from .datastore import Address, Datastore
from .hypertext import RawHypertext

link = parsy.regex(r"\$([awq]?[1-9][0-9]*)")
otherstuff = parsy.regex(r"[^\[\$\]]+")

lbrack = parsy.string("[")
rbrack = parsy.string("]")

@parsy.generate
def subnode():
    yield lbrack
    result = yield hypertext
    yield rbrack
    return result

hypertext = (link | subnode | otherstuff).many()

# MyPy can't deal with this yet
# ParsePiece = Union[str, "ParsePiece"]
ParsePiece = Any

def recursively_create_hypertext(
        pieces: List[ParsePiece],
        db: Datastore,
        pointer_link_map: Dict[str, Address]
        ) -> RawHypertext:
    result: List[Union[Address, str]] = []
    for piece in pieces:
        if isinstance(piece, list):
            result.append(recursively_insert_hypertext(piece, db, pointer_link_map))
        else:
            try:
                # This is a link that should be in the map
                result.append(pointer_link_map[link.parse(piece)])
            except parsy.ParseError:
                # This is just a regular string
                result.append(piece)
    return RawHypertext(result)


def recursively_insert_hypertext(
        pieces: List[ParsePiece],
        db: Datastore,
        pointer_link_map: Dict[str, Address]
        ) -> Address:
    result = db.insert(recursively_create_hypertext(pieces, db, pointer_link_map))
    return result


def insert_raw_hypertext(
        content: str,
        db: Datastore,
        pointer_link_map: Dict[str, Address],
        ) -> Address:
    parsed = hypertext.parse(content)
    return recursively_insert_hypertext(parsed, db, pointer_link_map)


def create_raw_hypertext(
        content: str,
        db: Datastore,
        pointer_link_map: Dict[str, Address]
        ) -> RawHypertext:
    parsed = hypertext.parse(content)
    return recursively_create_hypertext(parsed, db, pointer_link_map)
