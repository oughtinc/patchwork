import uuid

from typing import Any, List, Dict


# REVISIT: Plausibly this should be generic over the addressed
# content.
class Address(object):
    def __init__(self, db: "Datastore") -> None:
        self.location = uuid.uuid1()
        self.db = db

    def __hash__(self) -> int:
        return hash(self.location)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Address):
            return False
        return self.location == other.location

    def __str__(self) -> str:
        return repr(self)

    def __repr__(self) -> str:
        return "Address({})".format(self.location)


class Datastore(object):
    def __init__(self) -> None:
        self.content: Dict[Address, Any] = {} # Map from canonical address to content
        self.canonical_addresses: Dict[Any, Address] = {} # Map from content to canonical address
        self.promises: Dict[Address, List[Any]] = {} # Map from alias to list of promisees
        self.aliases: Dict[Address, Address] = {} # Map from alias to canonical address

    def dereference(self, address: Address) -> Any:
        return self.content[self.canonicalize(address)]

    def is_canonical(self, address: Address) -> bool:
        return address in self.content

    def canonicalize(self, address: Address) -> Address:
        return self.aliases.get(address) or address

    def make_promise(self) -> Address:
        address = Address(self)
        self.promises[address] = []
        return address

    def register_promisee(self, address: Address, promisee: Any) -> None:
        self.promises[address].append(promisee)

    def resolve_promise(self, address: Address, content: Any) -> List[Any]:
        if content in self.canonical_addresses:
            self.aliases[address] = self.canonical_addresses[content]
        else:
            self.content[address] = content
            self.canonical_addresses[content] = address
        promisees = self.promises[address]
        del self.promises[address]
        return promisees

    def insert(self, content: Any) -> Address:
        if content in self.canonical_addresses:
            print("duplicate")
            return self.canonical_addresses[content]

        address = self.make_promise()
        self.resolve_promise(address, content)
        return address

    def is_fulfilled(self, address: Address) -> bool:
        address = self.canonicalize(address)
        return address in self.content

