from collections import defaultdict, deque
from textwrap import indent
from typing import DefaultDict, Dict, Deque, Generator, List, Optional, Set, Tuple

from .datastore import Address, Datastore
from .hypertext import Workspace, visit_unlocked_region
from .text_manipulation import make_link_texts


def _can_advance_promise(db: Datastore, wsaddr: Address, promise: Address) \
        -> bool:
    """See :py:meth:`Context.can_advance_promise`."""
    ws_promises = db.dereference(wsaddr).promises

    if promise in ws_promises:
        return True

    promisee_wsaddrs = (args[0]  # = workspace link of promisee context
                        for p in ws_promises
                        for args in db.get_promisees(p))
    return any(_can_advance_promise(db, pwsa, promise)
               for pwsa in promisee_wsaddrs)


class Context(object):
    def __init__(
            self,
            workspace_link: Address,
            db: Datastore,
            unlocked_locations: Optional[Set[Address]]=None,
            parent: Optional["Context"]=None,
            ) -> None:

        # Unlocked locations should be in terms of the passed in workspace_link.

        self.workspace_link = workspace_link
        workspace = db.dereference(workspace_link)
        if unlocked_locations is not None:
            self.unlocked_locations = unlocked_locations
            self.unlocked_locations.add(self.workspace_link)
        else:
            # All of the things that are visible in a context with no explicit unlocks.
            self.unlocked_locations = set(
                    [workspace_link, workspace.question_link, workspace.scratchpad_link] +
                    [q for q, a, w in workspace.subquestions] +
                    ([workspace.predecessor_link] if workspace.predecessor_link else []))

        self.pointer_names, self.name_pointers = self._name_pointers(self.workspace_link, db)
        self.display = self.to_str(db)
        self.parent = parent

    def _name_pointers(
            self,
            workspace_link: Address,
            db: Datastore,
            ) -> Tuple[Dict[Address, str], Dict[str, Address]]:
        pointers: Dict[Address, str] = {}
        backward_pointers: Dict[str, Address] = {}

        def assign(link, string):
            pointers[link] = string
            backward_pointers[string] = link

        workspace_root = db.dereference(workspace_link)
        for i, subquestion in reversed(list(enumerate(workspace_root.subquestions, start=1))):
            q, a, w = subquestion
            assign(q, "$q{}".format(i))
            assign(a, "$a{}".format(i))
            assign(w, "$w{}".format(i))

        count = 0
        for your_link in visit_unlocked_region(self.workspace_link, workspace_link, db, self.unlocked_locations):
            your_page = db.dereference(your_link)
            for visible_link in your_page.links():
                if visible_link not in pointers:
                    count += 1
                    assign(visible_link, "${}".format(count))

        return pointers, backward_pointers

    def unlocked_locations_from_workspace(
            self,
            workspace_link: Address,
            db: Datastore,
            ) -> Set[Address]:
        result = set(visit_unlocked_region(self.workspace_link, workspace_link, db, self.unlocked_locations))
        return result

    def name_pointers_for_workspace(
            self,
            workspace_link: Address,
            db: Datastore
            ) -> Dict[str, Address]:
        return self._name_pointers(workspace_link, db)[1]

    def to_str(self, db: Datastore) -> str:
        CONTEXT_FMT = "{predecessor}Question: {question}\nScratchpad: {scratchpad}\nSubquestions:\n{subquestions}\n"

        link_texts = make_link_texts(self.workspace_link, db, self.unlocked_locations, self.pointer_names)

        subquestion_builder = []
        workspace: Workspace = db.dereference(self.workspace_link)
        for i, subquestion in enumerate(workspace.subquestions, start=1):
            q, a, w = subquestion
            q_text = link_texts[q]
            a_text = link_texts[a]
            w_text = link_texts[w]
            subquestion_builder.append("{}.\n{}\n{}\n{}".format(i, indent(q_text, "  "), indent(a_text, "  "), indent(w_text, "  ")))
        subquestions = "\n".join(subquestion_builder)

        if workspace.predecessor_link is None:
            predecessor = ""
        else:
            predecessor = "Predecessor: {}\n".format(link_texts[workspace.predecessor_link])

        return CONTEXT_FMT.format(
                predecessor=predecessor,
                question=link_texts[workspace.question_link],
                scratchpad=link_texts[workspace.scratchpad_link],
                subquestions=subquestions)

    def is_own_ancestor(self, db: Datastore) -> bool:
        initial_workspace = db.canonicalize(self.workspace_link)
        context: Optional[Context] = self.parent
        while context is not None:
            if context == self and db.canonicalize(context.workspace_link) == initial_workspace:
                return True
            context = context.parent
        return False

    # Note: The definition is mutually recursive, but we can implement it
    # with simple recursion, because we can obtain workspaces from the
    # datastore without constructing contexts.
    def can_advance_promise(self, db: Datastore, promise: Address) -> bool:
        """Determine if ``self`` can advance ``promise``.

        A context c can advance a promise p iff its workspace can advance p.

        A workspace w can advance a promise p iff
        - p is one of w's promises P(w) or
        - one of the promisees of the promises P(w) can advance P.
        The promisees of P(w) are contexts.
        """
        return _can_advance_promise(db, self.workspace_link, promise)


    def __str__(self) -> str:
        return self.display

    def __hash__(self) -> int:
        return hash(str(self))

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Context):
            return NotImplemented
        return self.workspace_link == other.workspace_link \
            and self.unlocked_locations == other.unlocked_locations \
            and self.parent == other.parent


