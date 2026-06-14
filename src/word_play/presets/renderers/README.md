# Renderer System

This document explains the philosophy, architecture, and interface of the renderer system in `word_play`.

Relevant implementation files:

- [core/rendering.py](../../core/rendering.py)
- [core/environment.py](../../core/environment.py)
- [renderers/__init__.py](./__init__.py)
- [renderers/layout.py](./layout.py)
- [pygame_renderer/renderer.py](./pygame_renderer/renderer.py)
- [pygame_renderer/extractors.py](./pygame_renderer/extractors.py)
- [pygame_renderer/draw.py](./pygame_renderer/draw.py)
- [pygame_renderer/runtime.py](./pygame_renderer/runtime.py)
- [pygame_renderer/assets.py](./pygame_renderer/assets.py)
- [pygame_renderer/replay_and_live.py](./pygame_renderer/replay_and_live.py)

It is written for two audiences:

- someone who wants a quick mental model of how rendering works
- someone who wants to extend an existing renderer or build a new one

## Approach In One Minute

The renderer system is designed around a strict separation:

- environments own simulation state
- environments may publish renderer-neutral render hints and transient render events
- renderers inspect the environment and build a per-frame scene
- a backend draws that scene
- renderer-private mutable state stays on the renderer side, not on the environment

The intent is:

- any renderer should be able to attach to any environment without requiring environment code changes
- environments and components should not depend on a specific renderer implementation
- renderer authors should only need to care about the entities, components, and events they want to visualize
- unknown components or unrelated systems should be ignored safely

## Design Philosophy

The renderer is not part of the simulation.

That sounds obvious, but it drives most of the architecture:

- simulation logic should not need to know whether the active renderer is pygame, ascii, graph-based, or something custom
- renderer-private state like selection, damage flash timers, image caches, and window state should not live on the environment
- renderers should observe the world, not own the world

In practice this means there are three different kinds of rendering data:

1. Public render input
   This is environment-owned data that renderers are allowed to observe.

2. Per-frame derived scene data
   This is built by a renderer from the environment and then consumed by the backend.

3. Renderer-private runtime state
   This is mutable state owned by a renderer instance, such as caches and transient visual bookkeeping.

Keeping those separate is what allows the renderer system to stay general and easy to extend.

## Core Types

The core rendering interfaces live in [core/rendering.py](../../core/rendering.py).

### `Renderer_State`

`Renderer_State` is the public render-facing state attached to the environment in [core/rendering.py](../../core/rendering.py).

It has two fields:

- `frame: dict[str, Any]`
- `events: list[Render_Event]`

Use `frame` for persistent or frame-wide render hints.

Examples:

- world bounds
- a preferred floor sprite
- HUD visibility
- overlay metadata

Use `events` for transient semantic signals.

Examples:

- `"speech"`
- `"hit"`
- `"notification"`
- `"selection_changed"` if a renderer wants to expose that semantically

Events are added through:

```python
env.render_state.emit("speech", entity=speaker, text="hello", step=env.cur_step + 1)
```

Important rule:

- `Renderer_State` is renderer-neutral public data
- it should not hold backend caches or implementation-specific viewer state

### `Render_Event`

`Render_Event` is a tiny semantic message defined in [core/rendering.py](../../core/rendering.py):

```python
Render_Event(kind: str, payload: dict[str, Any])
```

The event name should describe meaning, not implementation.

Good:

- `"speech"`
- `"hit"`
- `"overlay"`

Bad:

- `"pygame_bubble"`
- `"ascii_row"`
- `"sprite_flash_pass_2"`

### `Render_Scene`

`Render_Scene` is the per-frame output built by a renderer before drawing in [core/rendering.py](../../core/rendering.py).

It currently has:

- `metadata: dict[str, Any]`
- `layers: dict[str, list[Any]]`

Think of it as a renderer-internal scene graph in a deliberately lightweight form.

Examples of current layer names:

- `"world.renderables"`
- `"world.background_tiles"`
- `"ui.speech_bubbles"`
- `"effects.entity_hits"`

Examples of metadata currently used:

- `"simulation.step"`
- `"simulation.is_replay"`
- `"ui.hud_visible"`
- `"ui.sidebar"`

`Render_Scene` is intentionally plain data. Most code should access `scene.metadata[...]` and `scene.layers[...]` directly.

### `Render_Context`

`Render_Context` is renderer-private mutable state that lives across frames in [core/rendering.py](../../core/rendering.py).

It contains:

- `private: dict[object, Any]`

Its one important helper is:

```python
context.value_for(owner, factory)
```

This lazily creates stable private state for a specific renderer subsystem, extractor, or layout object.

That is useful for:

- layout runtime state
- previous health values
- damage flash timers
- animation state
- selection/focus state if a renderer wants to keep that there

The important property is ownership:

- `Render_Context` belongs to the renderer
- `Renderer_State` belongs to the environment

### `Renderer`

Every renderer implements the `Renderer` interface in [core/rendering.py](../../core/rendering.py):

```python
class Renderer(ABC):
    def create_renderer_state(self) -> Renderer_State: ...
    def create_render_context(self) -> Render_Context: ...
    def render(self, env: Environment) -> Render_Result: ...
```

At minimum, a renderer:

- decides on a default `Renderer_State`
- keeps any private runtime state it needs
- renders one frame from the environment

### `Render_Extractor`

Extractors are the main extension point, via `Render_Extractor` in [core/rendering.py](../../core/rendering.py).

```python
class Render_Extractor(ABC):
    def extract(
        self,
        env: Environment,
        render_state: Renderer_State,
        scene: Render_Scene,
        context: Render_Context,
    ) -> None:
        ...
```

An extractor is a small renderer-side object that knows how to observe one slice of the environment and contribute scene data.

Examples:

- one extractor can turn `Renderable` components into `"world.renderables"`
- another can turn `"speech"` events into `"ui.speech_bubbles"`
- another can generate graph edges from a custom relationship component

Extractors are where most renderer-specific interpretation should live.

## Frame Lifecycle

The typical flow for one frame is:

1. simulation state already exists on the environment
2. systems may emit semantic render events into `env.render_state`
3. `env.render()` calls the active renderer
4. the renderer builds a fresh `Render_Scene`
5. each extractor contributes to the scene
6. the backend draws the scene
7. environment-owned transient events are cleared after rendering

The `env.render()` entry point lives in [core/environment.py](../../core/environment.py), and the current pygame renderer’s frame assembly happens in [pygame_renderer/renderer.py](./pygame_renderer/renderer.py).

The key point is that the scene is rebuilt every frame, while renderer-private runtime state persists across frames.

## Ownership And Lifetime

This is the most important section for avoiding confusion.

### Put data in `Renderer_State` when:

- the environment wants to publish a semantic render hint
- the data should be renderer-neutral
- the data is safe for any renderer to ignore
- the data might reasonably be serialized or replayed

Examples:

- `env.render_state.frame["world.floor_sprite"] = ...`
- `env.render_state.frame["ui.sidebar"] = ...`
- `env.render_state.emit("speech", ...)`
- `env.render_state.emit("hit", ...)`

### Put data in `Render_Context` when:

- it is mutable renderer-private state
- it persists across frames
- it should not be environment-owned
- it should not be part of the public render contract

Examples:

- layout-specific cached offsets
- previous health values for flash detection
- animation progress owned by a renderer

### Put data in backend runtime state when:

- it is backend machinery, not semantic render state

Examples in the pygame renderer:

- image caches
- scaled image caches
- wall sprite caches
- vignette cache
- window size

### Put data in `Render_Scene` when:

- it is derived for the current frame
- it is what the draw backend should consume

Examples:

- visible sprites this frame
- visible background tiles this frame
- speech bubbles to draw this frame

## Current Pygame Architecture

The default pygame renderer is a useful example of the intended structure.

Files:

- [pygame_renderer/renderer.py](./pygame_renderer/renderer.py)
- [pygame_renderer/extractors.py](./pygame_renderer/extractors.py)
- [pygame_renderer/draw.py](./pygame_renderer/draw.py)
- [pygame_renderer/runtime.py](./pygame_renderer/runtime.py)
- [layout.py](./layout.py)

### Renderer

`Pygame_Renderer` in [pygame_renderer/renderer.py](./pygame_renderer/renderer.py):

- owns a `Render_Context`
- owns an ordered list of extractors
- builds a `Render_Scene`
- delegates actual drawing to `draw.py`

### Extractors

The default extractor list in [pygame_renderer/extractors.py](./pygame_renderer/extractors.py) currently includes:

- `Frame_Metadata_Extractor`
- `Visible_Renderables_Extractor`
- `Background_Tiles_Extractor`
- `Speech_Bubble_Extractor`
- `Hit_Effect_Extractor`

These are intentionally small and focused.

### Runtime

The pygame renderer keeps private runtime state in a typed runtime object split into buckets in [pygame_renderer/runtime.py](./pygame_renderer/runtime.py):

- `session`
- `view`
- `effects`

This split is not part of the public core API. It is just an implementation choice for the pygame renderer.

Roughly:

- `session` holds backend caches and window state
- `view` holds selection/focus and other viewer interaction state
- `effects` holds transient visual bookkeeping such as damage flash state

### Layout

Layouts in [layout.py](./layout.py) map environment positions into renderer space and may also provide background tiles.

Important:

- layouts are renderer-side helpers
- environments do not need to know which layout a renderer uses

`SinglePointLayout` in [layout.py](./layout.py) uses renderer-private layout runtime state through `Render_Context` instead of mutating the environment.

## How Environments Communicate With Renderers

Environments should stay simple.

The environment-facing rendering API should remain very small. The actual implementation is in [core/environment.py](../../core/environment.py):

- `env.render_state.frame[...]`
- `env.render_state.emit(...)`
- `env.render()`

That is intentionally minimal.

There are two main patterns for exposing information to renderers.

### Pattern 1: Extract from model state

If information is durable and naturally part of the world model, store it on entities/components and let an extractor read it.

Examples:

- positions
- health
- inventory
- graph relationships
- ownership
- faction

### Pattern 2: Emit semantic events

If information is transient and presentation-oriented, publish a generic render event.

Examples:

- speech bubbles
- hit flashes
- floating damage text
- “goal completed” notifications

The important rule is:

- environment code may publish renderer-neutral semantics
- environment code should not call renderer-specific methods or mention backend details

## How To Add A New Feature To An Existing Renderer

There are two common cases.

### Case A: The feature can be inferred from model state

Example: draw relationship lines between entities with a custom `Bond` component.

Recommended steps:

1. write a new extractor that looks for the component(s) you care about
2. have it contribute a new scene layer or metadata entry
3. update the backend draw code to render that layer if present
4. add the extractor to the renderer’s extractor list

The environment and components do not need to know anything about the renderer.

### Case B: The feature is a transient signal

Example: show a speech bubble or a hit flash.

Recommended steps:

1. have the relevant system emit a semantic event into `env.render_state`
2. write or extend an extractor that consumes that event kind
3. draw the resulting scene contribution in the backend

Again, the environment does not need to know which renderer is active.

## How To Add A New Extractor

A good extractor should:

- care about one coherent concern
- read only the env state it actually needs
- ignore unrelated entities/components
- contribute renderer-neutral scene data
- keep renderer-private cross-frame state in `Render_Context` if needed

Skeleton:

```python
class MyExtractor(Render_Extractor):
    def extract(self, env, render_state, scene, context) -> None:
        items = []
        for entity in env.state.entities:
            component = entity.get_component(MyComponent)
            if component is None:
                continue
            items.append(
                {
                    "entity": entity,
                    "value": component.some_value,
                }
            )
        scene.layers["my.layer"] = items
```

If you need persistent renderer-private state:

```python
from dataclasses import dataclass

@dataclass
class MyRuntimeState:
    previous_values: dict = None

class MyExtractor(Render_Extractor):
    def extract(self, env, render_state, scene, context) -> None:
        runtime = context.value_for(self, MyRuntimeState)
        ...
```

## How To Add A New Renderer

The expected workflow is:

1. decide what kind of scene representation your renderer wants to draw
2. decide which extractors you want
3. implement a renderer class
4. implement a backend draw pass for your scene
5. optionally define renderer-specific defaults in `create_renderer_state()`

Minimum skeleton:

```python
class MyRenderer(Renderer):
    def __init__(self, extractors: list[Render_Extractor] | None = None):
        self.render_context = self.create_render_context()
        self.extractors = extractors or []

    def create_renderer_state(self) -> Renderer_State:
        state = Renderer_State()
        return state

    def extract_scene(self, env) -> Render_Scene:
        scene = Render_Scene()
        for extractor in self.extractors:
            extractor.extract(env, env.render_state, scene, self.render_context)
        return scene

    def render(self, env) -> Render_Result:
        scene = self.extract_scene(env)
        self.draw(scene)
        return Render_Result()
```

Important:

- a renderer should not require changes to environments or components
- a renderer should only depend on the components/events it chooses to support
- unknown data should be ignored, not treated as an error

## A Practical Strategy For New Renderers

When starting a renderer, aim for a layered rollout. The pygame renderer in [pygame_renderer](./pygame_renderer/) is the current reference implementation.

### Stage 1: Generic fallback view

Support very general concepts first:

- entities with positions
- labels from entity names
- component names or summaries

This makes the renderer broadly usable across arbitrary environments.

### Stage 2: Optional richer adapters

Then add specialized extractors for common or optional components.

Examples:

- `Renderable`
- `Health`
- custom graph components
- conversation or quest-related events

This preserves generality while allowing richer views where the data exists.

## Conventions

### Prefer semantic event names

Good:

- `"speech"`
- `"hit"`
- `"overlay"`

Bad:

- `"pygame_hit_effect"`
- `"ascii_hint"`

### Prefer renderer-neutral scene contributions

A scene layer should describe what should be drawn, not how pygame should draw it.

Good:

- bubble text
- tile coordinates
- sprite identifier
- edge between entity A and entity B

Bad:

- raw `pygame.Surface`
- backend-only window coordinates as the main semantic representation

### Keep extractors small

If one extractor starts handling:

- sprites
- health bars
- speech
- inventory badges
- selection logic

then it is probably doing too much.

### Do not put backend machinery in `Renderer_State`

Avoid storing things like:

- image caches
- font objects
- selection rectangles
- window handles
- backend-specific surfaces

Those belong to the renderer side.

## Anti-Patterns

Avoid these:

- environment code that calls a specific renderer directly
- components with methods like `render_pygame()` or `to_ascii()`
- renderer-private state stored on the environment
- transient visual state written into simulation components just to satisfy the renderer
- one huge renderer class that knows about every possible component

## A Good Rule Of Thumb

When adding rendering-related functionality, ask:

1. Is this public semantic input from the environment?
   Put it in `Renderer_State`.

2. Is this derived only for the current frame?
   Put it in `Render_Scene`.

3. Is this mutable renderer-private state that persists across frames?
   Put it in `Render_Context` or renderer backend runtime state.

4. Is this backend machinery?
   Keep it inside the backend implementation.

If those four answers stay clear, the renderer system tends to remain simple and robust.

## Current Limitations

The current architecture is intentionally lightweight, but it is still evolving.

A few things to keep in mind:

- scene layers are still mostly string-keyed dictionaries and lists
- the pygame renderer is currently the most developed backend
- `Renderable` is effectively a pygame-oriented optional component, not a universal requirement
- different renderers may choose different scene conventions

That is acceptable for now because the key boundary is already in place:

- environments publish renderer-neutral data
- renderers decide how to observe and visualize it

## Summary

The renderer system is built around one central idea:

- environments expose semantic state and events
- renderers extract only what they care about
- backends draw derived scene data
- renderer-private mutable state stays on the renderer side

If you follow that rule, it becomes straightforward to:

- add new visual features to an existing renderer
- add a new renderer without changing environments
- support arbitrary environments with arbitrary components
- ignore irrelevant data safely
