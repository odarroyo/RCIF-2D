# 2D RC Building Analysis with Infill Walls

## Overview

`app_2d_building_analysis_infills.py` is a Streamlit-based application for creating and analyzing 2D reinforced concrete frame buildings **with masonry infill walls**. The app covers the full workflow:

- Definition of building geometry, RC materials, and cross-sections
- Assignment of structural elements (columns and beams) per floor
- Definition of masonry materials with configurable compressive strength and brick type
- Assignment of infill panels to individual bays of the building frame
- Modeling of infills as equivalent diagonal struts (X-pattern trusses) in OpenSeesPy
- Visualization of the infilled frame with color-coded panels
- Gravity and nonlinear pushover analysis with results visualization

The infill modeling follows the **equivalent strut approach** where each infill panel is represented by two diagonal truss elements forming an X-pattern. The masonry material uses the `Concrete01` uniaxial material with properties derived from the masonry compressive strength (f'm).

A video demonstration example is hosted at: https://youtu.be/hIw_ROFiXus

## Running the App

```bash

# Run the infills app
streamlit run app_2d_building_analysis_infills.py
```

## Tab-by-Tab Workflow

The app has **14 tabs** organized in sequential workflow:

| Tab | Name | Description |
|-----|------|-------------|
| 0 | **Load/New Model** | Start a new model or load an existing `.pkl` file |
| 1 | **Building Geometry** | Define X coordinates (column positions) and Y coordinates (story heights) |
| 2 | **Materials** | Create RC material sets (f'c, fy, detailing level: DES/DMO/PreCode) |
| 3 | **Masonry Materials** | Define masonry materials for infill walls (f'm, brick type) |
| 4 | **Sections** | Define rectangular RC cross-sections with reinforcement |
| 5 | **Element Assignment** | Assign sections to columns and beams per floor |
| 6 | **Model Visualization** | Review frame model, configure diaphragms, create OpenSeesPy elements |
| 7 | **Infill Assignment** | Assign infill walls to panels (thickness, material, width percentage) |
| 8 | **Loads and Mass Assignments** | Apply distributed beam loads, nodal masses, and nodal loads |
| 9 | **Save Model** | Export the complete model (including infills) to a `.pkl` file |
| 10 | **Python Script** | Generate a standalone Python script replicating the model |
| 11 | **Modal Analysis** | Compute natural periods and mode shapes |
| 12 | **Analysis** | Run gravity and pushover analysis |
| 13 | **Pushover Results** | Visualize pushover results (capacity curve, drifts, rotations) |

### Dependency Chain

The tabs enforce a strict sequential dependency. Each tab checks prerequisites before rendering:

```
Tab 0 (Load/New)
  --> Tab 1 (Geometry)          requires: nothing (or loaded data)
    --> Tab 2 (Materials)       requires: model_created
      --> Tab 3 (Masonry)       requires: model_created
        --> Tab 4 (Sections)    requires: materials defined
          --> Tab 5 (Assignment) requires: sections defined
            --> Tab 6 (Visualization / Create Elements)
                                requires: all assignments complete
                                (editing mode: all materials & sections confirmed)
              --> Tab 7 (Infills) requires: elements_created + masonry_materials
                --> Tab 8 (Loads) requires: elements_created
                  --> Tab 11 (Modal) requires: masses_assigned
                  --> Tab 12 (Analysis) requires: loads_applied
                    --> Tab 13 (Results) requires: pushover_analysis_done
```

Tabs 9 (Save) and 10 (Script) require `elements_created` but are otherwise independent.

---

## Tab 0: Load/New Model

Two modes:

- **New Model**: Resets all session state and initializes defaults.
- **Load Existing**: Loads a `.pkl` file. Infill data is loaded with backward compatibility — models saved without infill keys get empty defaults.

After loading a model, the user must:
1. Go to Tab 1 and click **"Create Model"** to recreate the OpenSeesPy model (calls `wipe()` + `model()` + `creategrid()` + `fixY()`)
2. Go to Tab 2 and confirm all RC materials (click "Confirm All" or confirm individually)
3. Go to Tab 4 and confirm all sections
4. Go to Tab 6 and click **"Create Elements"**
5. If the model had infills, go to Tab 7 and click **"Apply Infills to Model"**
6. Re-apply loads in Tab 8

This re-creation is necessary because OpenSeesPy state is in-process and does not persist across Streamlit sessions or page reloads.

### Model Validation

On load, the app checks for the presence of `coordz` — if found, it rejects the file as a 3D model.

---

## Tab 1: Building Geometry

Defines the 2D frame grid:

- **X Coordinates**: Comma-separated horizontal positions of column lines (e.g., `0, 5, 10, 15`)
- **Y Coordinates**: Comma-separated vertical positions of floor levels (e.g., `0, 3, 6, 9`). The first value must be `0` (base level).

On clicking **"Create Model"**:
1. Calls `lib.create_opensees_model(coordx, coordy)` which runs `wipe()`, `model('basic', '-ndm', 2, '-ndf', 3)`, `ut.creategrid(coordx, coordy)`, `fixY(0, 1, 1, 1)`
2. Computes diagonal node pairs for infill modeling: `lib.get_diagonal_node_pairs(coordx, coordy)` — stored in `session_state.diagonal_pairs` and `session_state.diagonal_lengths`
3. Resets `elements_created`, `loads_applied`, and `infills_assigned` flags

The geometry preview shows a Plotly scatter plot with nodes and grid lines.

---

## Tab 2: Materials (RC)

Defines reinforced concrete material sets. Each material requires:

| Parameter | Description | Range |
|-----------|-------------|-------|
| f'c (MPa) | Concrete compressive strength | 10–80 MPa |
| fy (MPa) | Steel yield strength | 200–700 MPa |
| Detailing | Seismic detailing level | DES, DMO, PreCode |

**Detailing levels** affect concrete confinement properties:
- **DES** (Special): High confinement — for seismic design category D/E
- **DMO** (Moderate): Moderate confinement — for seismic design category C
- **PreCode**: No confinement — for pre-code buildings

Materials are created in OpenSeesPy via `ut.col_materials(fc, fy, detailing, nps=3)`, which returns three tags: `(unctag, conftag, steeltag)` for unconfined concrete, confined concrete, and steel respectively.

**Tag generation**: `base_tag = (material_index + 1) * 100`, then `+1` (unconfined), `+2` (confined), `+3` (steel). For example, the first material gets tags 101, 102, 103.

---

## Tab 3: Masonry Materials

Each masonry material is defined by:

| Parameter | Description | Default | Range |
|-----------|-------------|---------|-------|
| Material Name | Descriptive label | "Masonry 1" | Any string |
| f'm (MPa) | Masonry compressive strength | 4.0 | 0.5–30.0 |
| Brick Type | Perforation type | VP | VP or HP |

### Elastic Modulus by Brick Type

| Brick Type | Full Name | Formula | Reference |
|------------|-----------|---------|-----------|
| **VP** | Vertical Perforation | Em = 775 * f'm | Guerrero et al. (2022) |
| **HP** | Horizontal Perforation | Em = 622 * f'm | Borah et al. (2021) |

### Concrete01 Material Parameters

The masonry material is modeled using the OpenSeesPy `Concrete01` uniaxial material, which defines a Kent-Scott-Park type stress-strain envelope:

```
uniaxialMaterial('Concrete01', matTag, fpc, epsc0, fpcu, epsU)
```

| Parameter | Symbol | Formula | Description |
|-----------|--------|---------|-------------|
| `fpc` | f'm | f'm * 1000 | Peak compressive stress (kN/m²) |
| `epsc0` | e0 | 2 * f'm / Em | Strain at peak stress |
| `fpcu` | fmu | 0.05 * f'm * 1000 | Residual/crushing stress (kN/m²) |
| `epsU` | emu | 2 * e0 | Ultimate/crushing strain |

> **Note**: Stresses are multiplied by 1000 to convert from MPa to kN/m² (the model's unit system). The residual stress ratio is **5%** of f'm (i.e., `fmu = 0.05 * f'm`).

### Stress-Strain Behavior

```
Stress (kN/m²)
  |
  |     * (f'm*1000, e0)
  |    / \
  |   /   \
  |  /     \_____ (fmu*1000, emu)
  | /
  |/__________________ Strain
  0     e0    emu
```

The `Concrete01` material only works in compression. The truss element formulation means each diagonal strut activates only when subjected to axial compression — tensile struts are effectively inactive due to the material's zero tensile strength.

### Tag Generation

Masonry material tags use **negative integers** starting at -1, decrementing for each additional material (-1, -2, -3, ...). This avoids collision with RC material tags (which are positive: 101, 102, 103, ...).

### Example Calculation

For VP brick with f'm = 4.0 MPa:
- Em = 775 * 4.0 = 3100 MPa
- e0 = 2 * 4.0 / 3100 = 0.00258
- fmu = 0.05 * 4.0 = 0.2 MPa
- emu = 2 * 0.00258 = 0.00516
- OpenSeesPy call: `Concrete01(-1, 4000, 0.00258, 200, 0.00516)`

### Material Deletion

When a masonry material is deleted, all infill assignments referencing that material are automatically reset to `'None'`.

---

## Tab 4: Sections

Defines rectangular RC cross-sections with fiber discretization. Each section requires:

| Parameter | Description |
|-----------|-------------|
| Height (H) | Section depth in meters |
| Width (B) | Section width in meters |
| Cover | Concrete cover in meters |
| Material | Which RC material set to use |
| Reinforcement | Bar sizes and counts per face (top, bottom, sides) |

Sections are created using `ut.create_rect_RC_section()`, which builds a fiber section with confined core, unconfined cover, and steel reinforcement layers.

Available rebar sizes (defined in `library_2d.py`):

| Name | Bar Size | Area (m²) |
|------|----------|-----------|
| As4 | #4 | 0.000127 m² |
| As5 | #5 | 0.0002 m² |
| As6 | #6 | 0.000286 m² |
| As7 | #7 | 0.000387 m² |
| As8 | #8 | 0.000508 m² |

---

## Tab 5: Element Assignment

Assigns sections to columns and beams for each floor. The UI presents a grid where each column position or span can be assigned a section or `'None'`.

- **Columns**: Assigned per X-position per floor. Setting a column to `'None'` removes it from the model.
- **Beams**: Assigned per span per floor. Setting a beam to `'None'` removes it.

When elements are removed (set to `'None'`), the corresponding nodes become "hanging" and are removed during element creation (Tab 6). This affects which panels are valid for infill placement.

---

## Tab 6: Model Visualization & Element Creation

This tab performs two functions:

### 1. Frame Visualization
Displays a Plotly figure of the 2D frame with columns and beams drawn according to their section dimensions and assignments.

### 2. Element Creation

Before creating elements, the user configures **rigid diaphragm constraints**:

| Mode | Description |
|------|-------------|
| All Floors | Apply rigid diaphragm to every floor (default) |
| Custom Selection | Choose specific floors for diaphragm constraints |
| No Diaphragms | No horizontal coupling between nodes |

Rigid diaphragms constrain all nodes at a floor level to move together horizontally — typical for floors with concrete slabs.

On clicking **"Create Elements"**:

1. Builds tag lists from section assignments via `lib.build_element_tags_list_2d()`
2. Creates nonlinear beam-column elements via `ut.create_elements2(coordx, coordy, building_columns, building_beams, output=1)` — returns `tagcols`, `tagbeams`, `column_info`, `beam_info`
3. Removes hanging nodes via `ut.remove_hanging_nodes(tagcols, tagbeams)`
4. Applies diaphragms via `ut.apply_diaphragms(floor_diaphragms, output=1)` where `floor_diaphragms` is a list of 0/1 values per floor
5. Stores `model_node_tags = getNodeTags()` for infill panel validity checks
6. Resets `loads_applied` and `infills_assigned` flags

---

## Tab 7: Infill Assignment

### Prerequisites
- Structural elements must be created first (Tab 6)
- At least one masonry material must be defined (Tab 3)

### Valid Panels

After element creation and hanging node removal, not all panels can receive infills. A panel is **valid** only if all 4 corner nodes exist in the model.

The function `get_valid_panels(coordx, coordy, model_node_tags)` checks each panel by computing the four corner node tags:

```python
# Node numbering convention: 1000 * (x_index + 1) + y_index
n_bl = 1000 * (span + 1) + (floor - 1)     # Bottom-left
n_br = 1000 * (span + 2) + (floor - 1)     # Bottom-right
n_tl = 1000 * (span + 1) + floor           # Top-left
n_tr = 1000 * (span + 2) + floor           # Top-right
```

A panel is valid if all four nodes exist in `model_node_tags`. Panels where columns or beams were assigned as `'None'` will be missing corner nodes and are automatically excluded.

### Visualization Legend

| Visual | Meaning |
|--------|---------|
| Shaded rectangle + X-pattern diagonal lines | Assigned infill (color-coded by material) |
| Dashed outline (gray) | Valid but unassigned panel |
| Not shown | Invalid panel (missing corner nodes) |

Different masonry materials are distinguished by fill color (orange, brown, sienna, etc.) with up to 5 colors cycling.

### Layout

The tab uses a two-column layout:
- **Left column (1/3 width)**: Controls — width percentage, floor selector, material selector, thickness, assignment method, clear/copy actions, summary metrics
- **Right column (2/3 width)**: Plotly frame visualization with infills + expandable assignments table

### Assignment Controls

| Control | Description | Default |
|---------|-------------|---------|
| **Width Percentage (w/d)** | Global ratio of equivalent strut width to diagonal length | 0.25 |
| **Floor Selector** | Multi-select: choose one or more floors | Floor 1 |
| **Masonry Material** | Dropdown: pick a masonry material or `'None'` to remove | First material |
| **Brick Thickness** | Wall thickness in meters | 0.10 m |
| **Assignment Method** | Radio: "Assign All Spans" or "By Span" | Assign All Spans |

**Width percentage references**:
- **0.25** — Priestley recommendation (d/4)
- **0.33** — Borah et al. recommendation (d/3)
- Range: 0.05 to 0.50 in steps of 0.05

### Assignment Methods

**Assign All Spans**: Applies the selected material and thickness to all valid spans on the selected floor(s) in a single action.

**By Span**: Shows a span selector dropdown with span boundaries (e.g., "Span 1 (0.00 → 5.00 m)"). Assigns only to the selected span on the selected floor(s). Warns if a panel is invalid.

### Batch Operations

| Button | Action |
|--------|--------|
| **Clear Selected Floors** | Resets all infill assignments on selected floors to `thickness=0.1`, `material_name='None'` |
| **Copy Configuration** | Copies infill assignments from a source floor to one or more target floors. Only copies to valid panels; invalid panels on the target get reset to defaults. |

### Summary Metrics

Displayed at the bottom of the controls column:
- **Valid Panels**: Total number of panels with all 4 corner nodes present
- **Assigned Infills**: Number of panels with a non-`'None'` material assigned

### Apply Infills to Model

After completing all assignments, click **"Apply Infills to Model"** to create the truss elements in OpenSeesPy. This button performs:

1. **Recreates masonry materials** in OpenSeesPy via `lib.col_infill()` for each defined masonry material (handles cases where `wipe()` was called or model was reloaded). Silently catches exceptions if materials already exist.

2. **Computes equivalent strut widths**: `building_infill_widths = lib.infill_widths(diagonal_lengths, width_percentage)` — multiplies each diagonal length by the width percentage.

3. **Builds thickness and material lists** from the session state assignments. For each panel:
   - If valid and assigned: uses the user-specified thickness and material tag
   - If invalid or unassigned: uses a negligible thickness (`1e-10`) and `'None'` material

4. **Computes strut cross-sectional areas**: `area = thickness * width` (element-wise multiplication of numpy arrays)

5. **Creates truss elements** via `lib.assign_infills(diagonal_pairs, building_infill_areas, building_infill_materials)` — two `Truss` elements per assigned panel

6. Reports the total count: `N_panels * 2` truss elements created

---

## Equivalent Strut Model

Each infill panel is modeled as two diagonal truss elements forming an **X-pattern**:

```
  node3 (TL) ───────── node2 (TR)
    │   ╲             ╱   │
    │     ╲         ╱     │
    │       ╲     ╱       │
    │         ╲ ╱         │
    │          ╳          │
    │         ╱ ╲         │
    │       ╱     ╲       │
    │     ╱         ╲     │
    │   ╱             ╲   │
  node1 (BL) ───────── node4 (BR)
```

### Node Mapping

The node numbering follows the OpenSeesPy grid convention `1000 * (x_index + 1) + y_index`:

| Corner | Variable | Formula | Description |
|--------|----------|---------|-------------|
| Bottom-Left | `nnode1` | `1000*(i+1) + j` | Where i = span index, j = floor index (0-based) |
| Top-Right | `nnode2` | `1000*(i+2) + j+1` | Diagonally opposite to nnode1 |
| Top-Left | `nnode3` | `1000*(i+1) + j+1` | Same X as nnode1, one floor up |
| Bottom-Right | `nnode4` | `1000*(i+2) + j` | Same Y as nnode1, one bay right |

### Truss Elements

| Truss | Nodes | Description |
|-------|-------|-------------|
| Truss 1 | nnode1 → nnode2 | Bottom-left to top-right diagonal |
| Truss 2 | nnode4 → nnode3 | Bottom-right to top-left diagonal |

Both trusses share the same cross-sectional area and material.

### Element Tagging

Infill truss elements use **negative tags** to distinguish them from structural elements (which have positive tags):

```
eltag1 = -1000*(floor+1) - 10*span
eltag2 = -1000*(floor+1) - 10*span - 1
```

Where `floor` is the 0-based floor index and `span` is the 0-based span index.

**Example**: Floor 0 (ground floor), Span 0:
- Truss 1 tag: `-1000*1 - 10*0 = -1000`
- Truss 2 tag: `-1000*1 - 10*0 - 1 = -1001`

Floor 2, Span 1:
- Truss 1 tag: `-1000*3 - 10*1 = -3010`
- Truss 2 tag: `-1000*3 - 10*1 - 1 = -3011`

### Why X-Pattern (Two Diagonals)?

Under lateral loading, one diagonal is in compression and the other in tension. Since the `Concrete01` material has zero tensile strength, only the compression diagonal activates at any given time. The X-pattern ensures that the infill resists lateral loads in both directions (left-to-right and right-to-left).

### Strut Geometry Calculation

```
diagonal_length = sqrt((x_right - x_left)^2 + (y_top - y_bot)^2)
strut_width = diagonal_length * width_percentage
strut_area = wall_thickness * strut_width
```

---

## Tab 8: Loads and Mass Assignments

This tab has three sub-tabs:

### Sub-tab 1: Distributed Loads on Beams

Two modes:
- **Same for All Floors**: Uniform load for typical floors (default 70 kN/m) and roof (default 50 kN/m). Uses `ut.load_beams()`.
- **Floor-wise (Custom)**: Individual load per beam, allowing different loads on each span of each floor. Uses `ut.load_beams2()`.

Loads are applied as negative values (downward in the Y direction).

### Sub-tab 2: Node Masses

Assigns translational masses (in tons) to nodes. Masses are required for modal analysis and dynamic analysis.

### Sub-tab 3: Nodal Loads

Applies concentrated forces at nodes. Useful for point loads not covered by distributed beam loads.

---

## Tab 9: Save Model

Exports the complete model to a `.pkl` file in the `models/` directory.

### Saved Data Structure

The pickle file contains a dictionary with these keys:

| Key | Type | Description |
|-----|------|-------------|
| `project_name` | str | Model identifier |
| `coordx` | list[float] | X coordinates |
| `coordy` | list[float] | Y coordinates |
| `materials` | dict | RC material definitions |
| `sections` | dict | Section definitions |
| `column_assignments` | dict | Column section assignments `{floor: {x_idx: section_name}}` |
| `beam_assignments` | dict | Beam section assignments `{floor: {span_idx: section_name}}` |
| `model_created` | bool | Geometry flag |
| `elements_created` | bool | Elements flag |
| `loads_applied` | bool | Loads flag |
| `masses_assigned` | bool | Masses flag |
| `nodal_loads_assigned` | bool | Nodal loads flag |
| `node_masses` | dict | Mass assignments |
| `node_loads` | dict | Nodal load assignments |
| `masonry_materials` | dict | Masonry material definitions (infill-specific) |
| `infill_assignments` | dict | Per-floor, per-span assignments `{floor: {span: {thickness, material_name}}}` |
| `width_percentage` | float | Global w/d ratio (infill-specific) |
| `infills_assigned` | bool | Whether infills were applied (infill-specific) |
| `load_type` | str | `'same'` or `'beamwise'` (if loads applied) |
| `floor_beam_loads` | float | Uniform floor load (if load_type='same') |
| `roof_beam_loads` | float | Uniform roof load (if load_type='same') |
| `beam_loads_beamwise` | dict | Per-beam loads (if load_type='beamwise') |

### Save Modes

- **New Model**: Simple save with user-specified filename
- **Editing Mode** (loaded model): Two options — "Overwrite Original" (with confirmation checkbox) or "Save As New" (with a different filename)

### Backward Compatibility

Models saved **without** infill keys load normally — the app uses `.get()` with defaults:
- `masonry_materials` defaults to `{}`
- `infill_assignments` defaults to `{}`
- `width_percentage` defaults to `0.25`
- `infills_assigned` defaults to `False`

---

## Tab 10: Python Script Generator

Generates a standalone Python script that replicates the current model configuration. The script can be run independently in any Python environment with OpenSeesPy and opseestools installed.

The generated script includes:
- Model setup (`wipe`, `model`, `creategrid`, `fixY`)
- Material definitions (RC and masonry)
- Section definitions
- Element creation
- Diagonal pair computation and infill assignment
- Load application
- Gravity analysis
- Pushover analysis setup

Useful for:
- Debugging model issues by comparing with the reference `master_script_infills_pushover_with_masses_and_nodal_loads.py`
- Running batch analyses outside the Streamlit UI
- Sharing models as portable Python scripts

---

## Tab 11: Modal Analysis

Computes modal properties of the structure using OpenSeesPy's `eigen()` and `modalProperties()` commands.

**Prerequisites**: Node masses must be assigned (Tab 8, Sub-tab 2).

**Number of modes**: `2 * n_floors` (2 DOF per floor for a 2D frame with diaphragm constraints).

**Output**: Natural frequencies (rad/s, Hz), periods (s), mode shapes, and modal participation factors. Results are displayed in a code block and can be downloaded as a text file.

---

## Tab 12: Analysis

Two sequential analyses:

### 1. Gravity Analysis

Runs `an.gravedad()` followed by `loadConst('-time', 0.0)` to lock in gravity loads as initial state.

### 2. Pushover Analysis

Nonlinear static pushover with displacement control:

| Parameter | Description | Default |
|-----------|-------------|---------|
| Target Drift Ratio (%) | Maximum drift as % of building height | 5.0% |
| Displacement Increment (m) | Step size for displacement control | 0.001 m |
| Control Node | Highest node tag from `getNodeTags()[-1]` (roof node) | Auto-selected |

The pushover uses `an.pushover2DRot()` from opseestools, which applies a lateral load pattern and performs displacement-controlled analysis while recording:
- Roof displacement (`dtecho`)
- Base shear (`Vbasal`)
- Story drifts (`drifts`)
- Member rotations (`rotations`)

Results are stored in `session_state.pushover_results` and can be saved as `.pkl` files.

---

## Tab 13: Pushover Results

Visualizes pushover analysis results with three sub-tabs:

### Pushover Curve
Base Shear (kN) vs. Roof Displacement (m) — the classic capacity curve.

### Capacity Curve
Base Shear vs. First Floor Drift Ratio — useful for identifying soft-story behavior.

### Interactive Drift Analysis
A time-step slider lets the user scrub through the pushover analysis and view:
- **Drift profile**: Story drift (%) vs. height (m) at the selected step
- **Member rotations**: Rotation demands at columns and beams at the selected step

Results can also be loaded from a previously saved `.pkl` file without re-running the analysis.

Summary metrics displayed: total analysis steps, maximum base shear, maximum roof displacement, and maximum roof drift ratio.

---

## Session State Variables

All persistent state is managed through Streamlit's `st.session_state`. The `initialize_session_state()` function sets defaults:

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `model_created` | bool | False | Whether geometry has been defined |
| `materials` | dict | {} | RC material definitions |
| `sections` | dict | {} | Section definitions |
| `column_assignments` | dict | {} | Column section assignments |
| `beam_assignments` | dict | {} | Beam section assignments |
| `elements_created` | bool | False | Whether elements have been created in OpenSeesPy |
| `loads_applied` | bool | False | Whether loads have been applied |
| `masses_assigned` | bool | False | Whether node masses have been assigned |
| `nodal_loads_assigned` | bool | False | Whether nodal loads have been assigned |
| `node_masses` | dict | {} | Mass values per node |
| `node_loads` | dict | {} | Load values per node |
| `gravity_analysis_done` | bool | False | Gravity analysis completed |
| `modal_analysis_done` | bool | False | Modal analysis completed |
| `pushover_analysis_done` | bool | False | Pushover analysis completed |
| `project_name` | str | "building_2d" | Model name |
| `coordx` | list/None | None | X coordinates |
| `coordy` | list/None | None | Y coordinates |
| `editing_mode` | bool | False | Whether a model was loaded (vs. new) |
| `loaded_model_name` | str/None | None | Filename of loaded model |
| `model_modified` | bool | False | Whether loaded model has been changed |
| `tagcols` | list/None | None | Column element tags from OpenSeesPy |
| `tagbeams` | list/None | None | Beam element tags from OpenSeesPy |
| `column_info` | obj/None | None | Column element metadata |
| `beam_info` | obj/None | None | Beam element metadata |
| `masonry_materials` | dict | {} | Masonry material definitions |
| `infill_assignments` | dict | {} | Infill panel assignments |
| `width_percentage` | float | 0.25 | Equivalent strut w/d ratio |
| `diagonal_pairs` | list/None | None | Node pairs for diagonal struts |
| `diagonal_lengths` | list/None | None | Diagonal lengths per panel |
| `infills_assigned` | bool | False | Whether infill trusses were created |
| `model_node_tags` | list/None | None | Active node tags after hanging node removal |

---

## Key Functions in `library_2d.py`

### Infill-Specific Functions

| Function | Location | Description |
|----------|----------|-------------|
| `get_diagonal_node_pairs(coordx, coordy)` | line ~988 | Returns floor-wise lists of diagonal node pairs `[nnode1, nnode2, nnode4, nnode3]` and diagonal lengths. Called during model creation (Tab 1). |
| `col_infill(fm, mat_tag, brick_type='VP')` | line ~1063 | Creates a `Concrete01` masonry material in OpenSeesPy. Computes Em, e0, fmu, emu from f'm and brick type. |
| `infill_widths(diagonal_lengths, width_percentage)` | line ~1090 | Multiplies diagonal lengths by width percentage to get strut widths. Returns nested list matching floor/span structure. |
| `assign_infills(diagonal_pairs, areas, materials)` | line ~1030 | Creates two diagonal `Truss` elements per panel. Skips panels where material is `'None'`. Uses negative element tags. |

### App-Level Helper Functions

| Function | Location | Description |
|----------|----------|-------------|
| `get_valid_panels(coordx, coordy, model_node_tags)` | app line ~1851 | Checks which panels have all 4 corner nodes present. Returns `{floor: {span: bool}}`. |
| `create_infill_frame_figure(...)` | app line ~1880 | Builds a Plotly figure showing the frame with infill panels color-coded by material. |

### General Functions Used

| Function | Source | Description |
|----------|--------|-------------|
| `lib.create_opensees_model()` | library_2d.py | Initializes 2D OpenSeesPy model with grid |
| `lib.parse_coordinates()` | library_2d.py | Parses comma-separated string to float list |
| `lib.generate_material_tags()` | library_2d.py | Generates positive integer tags for RC materials |
| `lib.create_material()` | library_2d.py | Creates RC material set in OpenSeesPy |
| `lib.build_element_tags_list_2d()` | library_2d.py | Converts assignments dict to nested tag list for `ut.create_elements2()` |
| `lib.create_2d_frame_figure()` | library_2d.py | Base frame Plotly visualization (without infills) |
| `ut.creategrid()` | opseestools | Creates 2D node grid |
| `ut.col_materials()` | opseestools | Creates confined/unconfined/steel material set |
| `ut.create_rect_RC_section()` | opseestools | Creates fiber section |
| `ut.create_elements2()` | opseestools | Creates nonlinear beam-column elements |
| `ut.remove_hanging_nodes()` | opseestools | Removes nodes with no connected elements |
| `ut.apply_diaphragms()` | opseestools | Applies rigid diaphragm constraints |
| `ut.load_beams()` / `ut.load_beams2()` | opseestools | Applies uniform/custom distributed loads |
| `an.gravedad()` | opseestools | Runs gravity analysis |
| `an.pushover2DRot()` | opseestools | Runs displacement-controlled pushover |

---

## Reference Scripts

| Script | Description |
|--------|-------------|
| `master_script_infills_pushover_with_masses_and_nodal_loads.py` | Standalone infill pushover example with masses and nodal loads. The reference implementation that this app replicates. Use it to verify results or as a template for batch analyses. |
| `master_script_IDA.py` | Incremental Dynamic Analysis example. |

---

## Units

| Quantity | Unit | Notes |
|----------|------|-------|
| Force | kN | |
| Length | m | |
| Mass | ton (Mg) | 1 ton = 1000 kg |
| Stress (user input) | MPa | f'c, fy, f'm entered in MPa |
| Stress (OpenSeesPy model) | kN/m² | MPa * 1000 |
| Time | seconds | |
| Distributed load | kN/m | Applied to beams |
| Strain | dimensionless | |

---

## Typical Workflow Example

1. **Start new model** (Tab 0)
2. **Define geometry**: `coordx = [0, 5, 10]`, `coordy = [0, 3, 6, 9]` → 2-bay, 3-story frame (Tab 1)
3. **Create RC material**: f'c=28 MPa, fy=420 MPa, DES detailing (Tab 2)
4. **Create masonry material**: f'm=4 MPa, VP bricks (Tab 3)
5. **Define sections**: Col 40x40, Beam 30x50 (Tab 4)
6. **Assign elements**: Columns and beams to all floors (Tab 5)
7. **Configure diaphragms** (all floors) and **create elements** (Tab 6)
8. **Assign infills**: Select all floors, choose masonry material, thickness=0.12m, assign all spans. Then click "Apply Infills to Model" (Tab 7)
9. **Apply loads**: 70 kN/m for floors, 50 kN/m for roof. Assign masses. (Tab 8)
10. **Save model** (Tab 9)
11. **Run modal analysis** to verify periods (Tab 11)
12. **Run gravity analysis**, then **pushover** with 5% target drift (Tab 12)
13. **View results**: capacity curve, drift profiles, rotation demands (Tab 13)

---

## Known Limitations and Notes

- The OpenSeesPy model state lives in the Python process and is lost on Streamlit page reload. Models must be recreated from the `.pkl` file each session.
- The `Concrete01` material for masonry does not capture tensile behavior — this is intentional for the compression-only strut model.
- The width percentage is a **global** parameter — all panels on all floors use the same w/d ratio. Per-panel width ratios are not supported.
- Maximum of ~10 spans per floor before infill element tags may collide (since the tag formula uses `-1000*(floor+1) - 10*span`, spans beyond 99 per floor would overflow).
- The script generator (Tab 10) references `ut.get_diagonal_node_pairs` which is the opseestools version; the app itself uses `lib.get_diagonal_node_pairs` from `library_2d.py`.
- Debug output is present in the element creation step (Tab 6) — the `st.write()` calls showing tag information are development artifacts.
