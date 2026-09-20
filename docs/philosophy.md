# Design

Use ordinary Python hints and dataclasses as the definition. Compile them once
into inspectable shapes, validate exact values, and construct ordinary objects.

The core owns types, constraints, defaults and their portable representation.
Consumers own input coercion, presentation, JSON text, function invocation and
checks requiring files, networks or application state.

Keep union selection explicit when types or portable spellings collide. Keep
missing values separate from `None`. Report the first error with its path.
Reject known contradictions during compilation without promising a general
satisfiability proof.

The vocabulary is closed. Compose existing types with dataclasses, lists, tuples
and unions. Use namespaced `Extra` strings for consumer-specific metadata;
layout and relations between fields belong to consumers. New core atoms require
semantics shared across multiple consumers.
