from collections import defaultdict, deque
from typing import Any, DefaultDict, Dict, List, Optional, Set, Union

import parsy

from .datastore import Address, Datastore
from .hypertext import RawHypertext, visit_unlocked_region

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


def make_link_texts(
        root_link: Address,
        db: Datastore,
        unlocked_locations: Optional[Set[Address]]=None,
        pointer_names: Optional[Dict[Address, str]]=None,
        ) -> Dict[Address, str]:
    INLINE_FMT = "[{pointer_name}: {content}]"
    ANONYMOUS_INLINE_FMT = "[{content}]"
    # We need to construct this string in topological order since pointers
    # are substrings of other unlocked pointers. Since everything is immutable
    # once created, we are guaranteed to have a DAG.
    include_counts: DefaultDict[Address, int] = defaultdict(int)

    for link in visit_unlocked_region(root_link, root_link, db, unlocked_locations):
        page = db.dereference(link)
        for visible_link in page.links():
            include_counts[visible_link] += 1

    assert(include_counts[root_link] == 0)

    no_incomings = deque([root_link])
    order: List[Address] = []
    while len(no_incomings) > 0:
        link = no_incomings.popleft()
        order.append(link)
        if unlocked_locations is None or link in unlocked_locations:
            page = db.dereference(link)
            for outgoing_link in page.links():
                include_counts[outgoing_link] -= 1
                if include_counts[outgoing_link] == 0:
                    no_incomings.append(outgoing_link)

    link_texts: Dict[Address, str] = {}

    if pointer_names is not None:
        for link in reversed(order):
            if link == root_link:
                continue
            if unlocked_locations is not None and link not in unlocked_locations:
                link_texts[link] = pointer_names[link]
            else:
                page = db.dereference(link)
                link_texts[link] = INLINE_FMT.format(
                        pointer_name=pointer_names[link],
                        content=page.to_str(display_map=link_texts))
    else:
        for link in reversed(order):
            page = db.dereference(link)
            link_texts[link] = ANONYMOUS_INLINE_FMT.format(
                    content=page.to_str(display_map=link_texts))


    return link_texts
