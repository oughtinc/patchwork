# Rudimentary Pure HCH

This repository contains an implementation of an
[HCH](https://ai-alignment.com/humans-consulting-hch-f893f6051455) test bed.

In the terms used by the
[Ought Taxonomy of approaches to capability
amplification](https://ought.org/projects/factored-cognition/taxonomy),
this program implements:

* One-shot question answering
* Recursion
* Pointers
* A weak form of Reflection, in which workspaces can be passed around and
   inspected, but certain actions are not reifiable (specifically pointer unlocking)
* Caching
* Lazy Evaluation

## Setup

In order to use this package, you'll need at least Python 3.6 and parsy 1.2.0.

## Usage

To begin, run

```bash
python -m pure_hch.main
```

### Interpreting a context
A context can have four fields:

1. A pointer to a predecessor workspace
2. A pointer to a question to be answered (unlocked)
3. A pointer to a scratchpad (unlocked) where intermediate work can be cached
4. A list of pointers to subquestions. The subquestions themselves are unlocked,
   but the answers and workspaces used to compute those answers are not.

#### Hypertext in contexts
Contexts contain pointers, which can be thought of as links to pages in a web of
hypertext. They are abstract references to data. A pointer can either
be "locked" or "unlocked". Locked pointers appear as `$[id]`, where `[id]` is either
a number, or a special identifier followed by a number. So `$12` is a locked pointer,
`$q1` is the locked pointer to your first subquestion, `$a1` is the locked pointer to
the first subquestion's answer, and `$w1` is the locked pointer to the workspace that
generated the first subquestion's answer.

Unlocked pointers appear inside square brackets, with the pointer id prepended to
the content of the data: `[$1: Hello, world]` represents an unlocked pointer to
hypertext containing the string `Hello, world`. Hypertext can either represent
a workspace (as in the `$w1` example), or can be "raw", representing some
unstructured text.

### Taking Actions

Four actions can be taken in any context:
1. `ask <subquestion>`: Ask a subquestion
2. `scratch <scratchpad_contents>`: replace the scratchpad contents with
  `<scratchpad_contents>`.
3. `unlock <pointer_id>`: Make a successor context that has
  the pointer `<pointer_id>` visible.
4. `reply <response>`

#### Hypertext Syntax

The `ask`, `scratch`, and `reply` commands all accept hypertext as an
argument. The hypertext you specify here is similar to the hypertext
that appears throughout the context, but is slightly different.

In particular, expanded pointers in your hypertext should not have
identifier prefixes. For example, you might
`ask is the list [a [b [c [d]]]] sorted?`. Otherwise, the hypertext
you construct is semantically identical to the hypertext in a context.

The `unlock` action accepts a pointer exactly as it appears in the context:
For example, `unlock $w1`.

> NOTE: This system is _lazy_. This means that unlocking a context automatically
puts the successor context on hold until the unlocked result is ready. However,
locked pointers can be _passed around_ arbitrarily before being unlocked. So if
I want to ask three questions in sequence, I can pass the answer of the first
to the second, and the answer of the second to the third, without unlocking anything.
When I unlock the third answer, my successor will not wake up until that answer is
actually available.
