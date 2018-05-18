from typing import Dict, List, Optional, Set, Tuple, Union

from .datastore import Address, Datastore

HypertextFragment = Union[Address, str]
Subquestion = Tuple[Address, Address, Address] # question, answer, final_workspace

class Hypertext(object):
    def links(self) -> List[Address]:
        raise NotImplementedError("Hypertext is a pure virtual class")

    def to_str(self, display_map: Optional[Dict[Address, str]]=None) -> str:
        raise NotImplementedError("Hypertext is a pure virtual class")

    def __str__(self) -> str:
        return self.to_str()

    def __eq__(self, other: object):
        if not isinstance(other, Hypertext):
            return False
        return str(self) == str(other)

    def __hash__(self):
        return hash(str(self))


class RawHypertext(Hypertext):
    def __init__(self, chunks: List[HypertextFragment]) -> None:
        self.chunks = chunks

    def links(self) -> List[Address]:
        result = []
        seen: Set[Address] = set()
        for chunk in self.chunks:
            if isinstance(chunk, Address) and chunk not in seen:
                seen.add(chunk)
                result.append(chunk)
        return result

    def to_str(self, display_map: Optional[Dict[Address, str]]=None) -> str:
        builder = []
        for chunk in self.chunks:
            if isinstance(chunk, str):
                builder.append(chunk)
            elif display_map is None:
                builder.append(str(chunk))
            else:
                builder.append(display_map[chunk])
        return ''.join(builder)


class Workspace(Hypertext):
    def __init__(
            self,
            question_link: Address,
            answer_promise: Address,
            final_workspace_promise: Address,
            scratchpad_link: Address,
            subquestions: List[Subquestion],
            predecessor_link: Optional[Address]=None,
            ) -> None:
        self.question_link = question_link
        self.answer_promise = answer_promise
        self.final_workspace_promise = final_workspace_promise
        self.scratchpad_link = scratchpad_link
        self.subquestions = subquestions
        self.predecessor_link = predecessor_link

    def links(self) -> List[Address]:
        result = []
        if self.predecessor_link is not None:
            result.append(self.predecessor_link)
        result.append(self.question_link)
        result.append(self.scratchpad_link)
        for q, a, w in self.subquestions:
            result.extend([q, a, w])
        return result

    def to_str(self, display_map: Optional[Dict[Address, str]]=None) -> str:
        builder = []
        if self.predecessor_link is not None:
            if display_map is None:
                predecessor = str(self.predecessor_link)
            else:
                predecessor = display_map[self.predecessor_link]
            builder.append("Predecessor: {}".format(predecessor))
        if display_map is None:
            question = str(self.question_link)
            scratchpad = str(self.scratchpad_link)
            subquestions = str(self.subquestions)
        else:
            question = display_map[self.question_link]
            scratchpad = display_map[self.scratchpad_link]
            subquestions = "\n".join("{}.\n  {},\n  {},\n  {}".format(i, display_map[q], display_map[a], display_map[w]) for i, (q, a, w) in enumerate(self.subquestions, start=1))
        builder.append("Question: {}")
        builder.append("Scratchpad: {}")
        builder.append("Subquestions: {}")
        return "\n".join(builder)

