bl_info = {
    "name": "Uncertainty Index",
    "author": "Tijm Lanjouw",
    "version": (0, 9),
    "blender": (4, 0, 0),
    "location": "View3D > Sidebar > Uncertainty",
    "description": "Allows assigning uncertainty classification to models",
    "warning": "",
    "doc_url": "",
    "category": "Object",
}

import bpy
import json
import csv
import os

# ---------------------------------------------------------------------------
# Built-in presets
# ---------------------------------------------------------------------------

BUILTIN_PRESETS = {
    "4DRL": [
        {"label": "Certain",            "color": [0.250158, 0.376262, 0.533276, 1.0]},
        {"label": "Quite Certain",      "color": [0.024761, 0.522505, 0.187029, 1.0]},
        {"label": "Moderately Certain", "color": [0.855158, 0.762264, 0.229617, 1.0]},
        {"label": "Not so Certain",     "color": [0.787660, 0.590824, 0.508875, 1.0]},
        {"label": "Quite Uncertain",    "color": [0.625514, 0.211733, 0.007954, 1.0]},
        {"label": "Very Uncertain",     "color": [0.459934, 0.056496, 0.008830, 1.0]},
    ],
}

# ---------------------------------------------------------------------------
# Label / colour update callbacks
# ---------------------------------------------------------------------------

def on_label_update(self, context):
    """When a class label changes, update all objects assigned to it."""
    scene = context.scene
    for i, uc in enumerate(scene.uncertainty_classes):
        if uc == self:
            for obj in bpy.data.objects:
                if obj.get("uncertainty_index") == i:
                    obj["uncertainty_label"] = uc.label
            break


def on_color_update(self, context):
    """When a class colour changes, update all objects assigned to it."""
    scene = context.scene
    for i, uc in enumerate(scene.uncertainty_classes):
        if uc == self:
            for obj in bpy.data.objects:
                if obj.get("uncertainty_index") == i:
                    obj.color = uc.color
            break

# ---------------------------------------------------------------------------
# Per-class property group
# ---------------------------------------------------------------------------

class UncertaintyClass(bpy.types.PropertyGroup):
    label: bpy.props.StringProperty(
        name="Label",
        default="Class",
        update=on_label_update
    )
    color: bpy.props.FloatVectorProperty(
        name="Color",
        subtype='COLOR',
        size=4,
        min=0.0, max=1.0,
        default=(0.8, 0.8, 0.8, 1.0),
        update=on_color_update,
    )

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def load_classes_from_list(scene, class_list):
    scene.uncertainty_classes.clear()
    for entry in class_list:
        uc = scene.uncertainty_classes.add()
        uc.label = entry["label"]
        uc.color = entry["color"]
    scene.uncertainty_class_index = 0


def classes_to_list(scene):
    return [
        {"label": uc.label, "color": list(uc.color)}
        for uc in scene.uncertainty_classes
    ]


def get_user_presets(scene):
    raw = scene.get("uncertainty_user_presets", "{}")
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {}


def save_user_presets(scene, presets_dict):
    scene["uncertainty_user_presets"] = json.dumps(presets_dict)


def get_all_preset_items(scene):
    """Return all preset names (built-in + user) as enum items."""
    items = []
    for name in BUILTIN_PRESETS:
        items.append((f"builtin::{name}", name, f"Built-in: {name}"))
    for name in get_user_presets(scene):
        items.append((f"user::{name}", name, f"User preset: {name}"))
    if not items:
        items.append(("NONE", "No Presets", ""))
    return items


def preset_items_callback(self, context):
    return get_all_preset_items(context.scene)


def is_object_color_active(context):
    """Return True if the active 3D viewport is showing Object Color."""
    for area in context.screen.areas:
        if area.type == 'VIEW_3D':
            shading = area.spaces.active.shading
            return (
                shading.type == 'SOLID' and
                shading.color_type == 'OBJECT'
            )
    return False


def set_object_color_display(context, enable):
    """Enable or disable Object Color display in all 3D viewports."""
    for area in context.screen.areas:
        if area.type == 'VIEW_3D':
            shading = area.spaces.active.shading
            if enable:
                shading.type = 'SOLID'
                shading.color_type = 'OBJECT'
                shading.light = 'STUDIO'
                shading.studio_light = 'paint.sl'
            else:
                shading.color_type = 'MATERIAL'
                shading.light = 'STUDIO'
                shading.studio_light = 'Default'

# ---------------------------------------------------------------------------
# Operators – classes
# ---------------------------------------------------------------------------

class OBJECT_OT_add_uncertainty_class(bpy.types.Operator):
    """Add a new uncertainty class"""
    bl_idname = "object.add_uncertainty_class"
    bl_label = "Add Class"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        context.scene.uncertainty_classes.add()
        context.scene.uncertainty_class_index = len(context.scene.uncertainty_classes) - 1
        return {'FINISHED'}


class OBJECT_OT_remove_uncertainty_class(bpy.types.Operator):
    """Remove the selected uncertainty class"""
    bl_idname = "object.remove_uncertainty_class"
    bl_label = "Remove Class"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        classes = context.scene.uncertainty_classes
        index = context.scene.uncertainty_class_index
        if not classes:
            self.report({'WARNING'}, "No classes to remove.")
            return {'CANCELLED'}
        classes.remove(index)
        context.scene.uncertainty_class_index = max(0, index - 1)
        return {'FINISHED'}


class OBJECT_OT_select_uncertainty_class(bpy.types.Operator):
    """Select this uncertainty class for assignment"""
    bl_idname = "object.select_uncertainty_class"
    bl_label = "Select Class"

    class_index: bpy.props.IntProperty()

    def execute(self, context):
        context.scene.uncertainty_class_index = self.class_index
        return {'FINISHED'}


class OBJECT_OT_assign_uncertainty_index(bpy.types.Operator):
    """Apply the selected uncertainty class to all selected objects and the active object"""
    bl_idname = "object.assign_uncertainty"
    bl_label = "Apply to Selection"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        classes = context.scene.uncertainty_classes
        index = context.scene.uncertainty_class_index

        if not classes:
            self.report({'WARNING'}, "No uncertainty classes defined.")
            return {'CANCELLED'}

        targets = set(context.selected_objects)
        if context.active_object:
            targets.add(context.active_object)

        if not targets:
            self.report({'WARNING'}, "No objects selected.")
            return {'CANCELLED'}

        uc = classes[index]
        for obj in targets:
            obj["uncertainty_index"] = index
            obj["uncertainty_label"] = uc.label
            obj.color = uc.color

        self.report({'INFO'}, f"Assigned '{uc.label}' to {len(targets)} object(s).")
        return {'FINISHED'}

# ---------------------------------------------------------------------------
# Operators – presets
# ---------------------------------------------------------------------------

class OBJECT_OT_load_selected_preset(bpy.types.Operator):
    """Load the preset selected in the dropdown"""
    bl_idname = "object.load_selected_preset"
    bl_label = "Load Preset"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        value = context.scene.uncertainty_preset_selector

        if value == "NONE":
            self.report({'WARNING'}, "No preset selected.")
            return {'CANCELLED'}

        if value.startswith("builtin::"):
            name = value[len("builtin::"):]
            preset = BUILTIN_PRESETS.get(name)
        elif value.startswith("user::"):
            name = value[len("user::"):]
            preset = get_user_presets(context.scene).get(name)
        else:
            self.report({'WARNING'}, "Unknown preset type.")
            return {'CANCELLED'}

        if not preset:
            self.report({'WARNING'}, f"Preset '{name}' not found.")
            return {'CANCELLED'}

        load_classes_from_list(context.scene, preset)
        self.report({'INFO'}, f"Loaded preset '{name}'.")
        return {'FINISHED'}


class OBJECT_OT_save_user_preset(bpy.types.Operator):
    """Save current classes as a named user preset"""
    bl_idname = "object.save_user_preset"
    bl_label = "Save Preset"
    bl_options = {'REGISTER', 'UNDO'}

    preset_name: bpy.props.StringProperty(name="Preset Name", default="My Preset")

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context):
        name = self.preset_name.strip()
        if not name:
            self.report({'WARNING'}, "Preset name cannot be empty.")
            return {'CANCELLED'}

        presets = get_user_presets(context.scene)
        presets[name] = classes_to_list(context.scene)
        save_user_presets(context.scene, presets)
        self.report({'INFO'}, f"Saved preset '{name}'.")
        return {'FINISHED'}


class OBJECT_OT_delete_selected_preset(bpy.types.Operator):
    """Delete the currently selected user preset"""
    bl_idname = "object.delete_selected_preset"
    bl_label = "Delete Preset"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        value = context.scene.uncertainty_preset_selector

        if not value.startswith("user::"):
            self.report({'WARNING'}, "Only user presets can be deleted.")
            return {'CANCELLED'}

        name = value[len("user::"):]
        presets = get_user_presets(context.scene)

        if name not in presets:
            self.report({'WARNING'}, f"Preset '{name}' not found.")
            return {'CANCELLED'}

        del presets[name]
        save_user_presets(context.scene, presets)
        self.report({'INFO'}, f"Deleted preset '{name}'.")
        return {'FINISHED'}

# ---------------------------------------------------------------------------
# Operator – toggle object color display
# ---------------------------------------------------------------------------

class OBJECT_OT_toggle_object_color_display(bpy.types.Operator):
    """Toggle viewport shading between Object Color and Material Color"""
    bl_idname = "object.toggle_object_color_display"
    bl_label = "Toggle Object Color Display"
    bl_options = {'REGISTER'}

    def execute(self, context):
        currently_active = is_object_color_active(context)
        set_object_color_display(context, not currently_active)
        state = "enabled" if not currently_active else "disabled"
        self.report({'INFO'}, f"Object color display {state}.")
        return {'FINISHED'}

# ---------------------------------------------------------------------------
# Operator – CSV export
# ---------------------------------------------------------------------------

class OBJECT_OT_export_uncertainty_csv(bpy.types.Operator):
    """Export object names and their uncertainty classifications to a CSV file"""
    bl_idname = "object.export_uncertainty_csv"
    bl_label = "Export to CSV"
    bl_options = {'REGISTER'}

    filepath: bpy.props.StringProperty(
        name="File Path",
        description="Path to save the CSV file",
        subtype='FILE_PATH',
        default="uncertainty_export.csv",
    )
    filter_glob: bpy.props.StringProperty(
        default="*.csv",
        options={'HIDDEN'},
    )
    only_assigned: bpy.props.BoolProperty(
        name="Only Assigned Objects",
        description="Export only objects that have an uncertainty class assigned",
        default=True,
    )

    def invoke(self, context, event):
        blend_path = bpy.data.filepath
        if blend_path:
            base = os.path.splitext(blend_path)[0]
            self.filepath = base + "_uncertainty.csv"
        else:
            self.filepath = "uncertainty_export.csv"
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

    def execute(self, context):
        filepath = bpy.path.abspath(self.filepath)

        if not filepath.lower().endswith(".csv"):
            filepath += ".csv"

        rows = []
        for obj in sorted(bpy.data.objects, key=lambda o: o.name):
            label = obj.get("uncertainty_label", None)
            idx   = obj.get("uncertainty_index", None)

            if self.only_assigned and label is None:
                continue

            rows.append({
                "Object Name":       obj.name,
                "Uncertainty Index": idx if idx is not None else "",
                "Uncertainty Label": label if label is not None else "",
            })

        if not rows:
            self.report({'WARNING'}, "No objects with uncertainty assignments found.")
            return {'CANCELLED'}

        try:
            with open(filepath, 'w', newline='', encoding='utf-8') as f:
                fieldnames = ["Object Name", "Uncertainty Index", "Uncertainty Label"]
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(rows)
        except OSError as e:
            self.report({'ERROR'}, f"Could not write file: {e}")
            return {'CANCELLED'}

        self.report({'INFO'}, f"Exported {len(rows)} object(s) to '{filepath}'.")
        return {'FINISHED'}

# ---------------------------------------------------------------------------
# Operator – viewport render with legend overlay
# ---------------------------------------------------------------------------

import gpu
import blf
import struct
import tempfile
from gpu_extras.batch import batch_for_shader

# Module-level handle kept for safety in case of unclean shutdown
_legend_draw_handle = None


def _linear_to_srgb(c):
    """Convert a single linear float channel to sRGB (gamma-corrected) float."""
    if c <= 0.0031308:
        return c * 12.92
    return 1.055 * (c ** (1.0 / 2.4)) - 0.055


def _build_legend_pixels(classes, width, height):
    """
    Build a flat RGBA pixel array (floats, Blender convention) of size width×height
    containing the legend box, ready to be blended onto a render.
    Returns a flat list of floats: [r,g,b,a, r,g,b,a, ...] bottom-row first.
    """
    # Layout constants (pixels) — doubled for legibility
    pad        = 28
    swatch_w   = 36
    swatch_h   = 28
    row_h      = 44

    n = len(classes)

    # Estimate label widths at ~12 px per character (doubled glyph width + gap)
    char_w     = 12
    max_chars  = max(len(uc.label) for uc in classes)
    label_w    = max_chars * char_w

    box_w = pad + swatch_w + pad + label_w + pad
    box_h = pad + n * row_h + pad

    # Position: bottom-left corner
    box_x = pad
    box_y = pad

    # Start with fully transparent canvas
    pixels = [0.0] * (width * height * 4)

    def set_pixel(x, y, r, g, b, a):
        if 0 <= x < width and 0 <= y < height:
            idx = (y * width + x) * 4
            pixels[idx]     = r
            pixels[idx + 1] = g
            pixels[idx + 2] = b
            pixels[idx + 3] = a

    def fill_rect(x0, y0, w, h, r, g, b, a):
        for dy in range(h):
            for dx in range(w):
                set_pixel(x0 + dx, y0 + dy, r, g, b, a)

    # Semi-transparent dark background
    fill_rect(box_x, box_y, box_w, box_h, 0.08, 0.08, 0.08, 0.75)

    # Draw each class row
    for i, uc in enumerate(classes):
        row_y = box_y + pad + i * row_h

        # Colour swatch
        sx = box_x + pad
        sy = row_y + (row_h - swatch_h) // 2
        r = _linear_to_srgb(uc.color[0])
        g = _linear_to_srgb(uc.color[1])
        b = _linear_to_srgb(uc.color[2])
        fill_rect(sx, sy, swatch_w, swatch_h, r, g, b, 1.0)

        # White 1px border around swatch
        for dx in range(swatch_w):
            set_pixel(sx + dx, sy,               1.0, 1.0, 1.0, 0.8)
            set_pixel(sx + dx, sy + swatch_h - 1, 1.0, 1.0, 1.0, 0.8)
        for dy in range(swatch_h):
            set_pixel(sx,                sy + dy, 1.0, 1.0, 1.0, 0.8)
            set_pixel(sx + swatch_w - 1, sy + dy, 1.0, 1.0, 1.0, 0.8)

        # Label text
        tx = sx + swatch_w + pad
        ty = row_y + (row_h - _FONT_GLYPH_H * 2) // 2
        _draw_text_pixels(pixels, width, height, tx, ty, uc.label, 1.0, 1.0, 1.0, scale=2)

    return pixels


# ---------------------------------------------------------------------------
# Minimal 5×7 bitmap font for pixel-text rendering
# ---------------------------------------------------------------------------

_FONT_5x7 = {
    ' ': [0,0,0,0,0,0,0],
    'A': [0b01110,0b10001,0b10001,0b11111,0b10001,0b10001,0b10001],
    'B': [0b11110,0b10001,0b10001,0b11110,0b10001,0b10001,0b11110],
    'C': [0b01110,0b10001,0b10000,0b10000,0b10000,0b10001,0b01110],
    'D': [0b11110,0b10001,0b10001,0b10001,0b10001,0b10001,0b11110],
    'E': [0b11111,0b10000,0b10000,0b11110,0b10000,0b10000,0b11111],
    'F': [0b11111,0b10000,0b10000,0b11110,0b10000,0b10000,0b10000],
    'G': [0b01110,0b10001,0b10000,0b10111,0b10001,0b10001,0b01110],
    'H': [0b10001,0b10001,0b10001,0b11111,0b10001,0b10001,0b10001],
    'I': [0b01110,0b00100,0b00100,0b00100,0b00100,0b00100,0b01110],
    'J': [0b00111,0b00010,0b00010,0b00010,0b00010,0b10010,0b01100],
    'K': [0b10001,0b10010,0b10100,0b11000,0b10100,0b10010,0b10001],
    'L': [0b10000,0b10000,0b10000,0b10000,0b10000,0b10000,0b11111],
    'M': [0b10001,0b11011,0b10101,0b10001,0b10001,0b10001,0b10001],
    'N': [0b10001,0b11001,0b10101,0b10011,0b10001,0b10001,0b10001],
    'O': [0b01110,0b10001,0b10001,0b10001,0b10001,0b10001,0b01110],
    'P': [0b11110,0b10001,0b10001,0b11110,0b10000,0b10000,0b10000],
    'Q': [0b01110,0b10001,0b10001,0b10001,0b10101,0b10010,0b01101],
    'R': [0b11110,0b10001,0b10001,0b11110,0b10100,0b10010,0b10001],
    'S': [0b01111,0b10000,0b10000,0b01110,0b00001,0b00001,0b11110],
    'T': [0b11111,0b00100,0b00100,0b00100,0b00100,0b00100,0b00100],
    'U': [0b10001,0b10001,0b10001,0b10001,0b10001,0b10001,0b01110],
    'V': [0b10001,0b10001,0b10001,0b10001,0b10001,0b01010,0b00100],
    'W': [0b10001,0b10001,0b10001,0b10101,0b10101,0b11011,0b10001],
    'X': [0b10001,0b10001,0b01010,0b00100,0b01010,0b10001,0b10001],
    'Y': [0b10001,0b10001,0b01010,0b00100,0b00100,0b00100,0b00100],
    'Z': [0b11111,0b00001,0b00010,0b00100,0b01000,0b10000,0b11111],
    'a': [0b00000,0b00000,0b01110,0b00001,0b01111,0b10001,0b01111],
    'b': [0b10000,0b10000,0b11110,0b10001,0b10001,0b10001,0b11110],
    'c': [0b00000,0b00000,0b01110,0b10000,0b10000,0b10001,0b01110],
    'd': [0b00001,0b00001,0b01111,0b10001,0b10001,0b10001,0b01111],
    'e': [0b00000,0b00000,0b01110,0b10001,0b11111,0b10000,0b01110],
    'f': [0b00110,0b01000,0b11100,0b01000,0b01000,0b01000,0b01000],
    'g': [0b00000,0b01111,0b10001,0b10001,0b01111,0b00001,0b01110],
    'h': [0b10000,0b10000,0b11110,0b10001,0b10001,0b10001,0b10001],
    'i': [0b00100,0b00000,0b00100,0b00100,0b00100,0b00100,0b00100],
    'j': [0b00010,0b00000,0b00110,0b00010,0b00010,0b10010,0b01100],
    'k': [0b10000,0b10010,0b10100,0b11000,0b10100,0b10010,0b10001],
    'l': [0b01100,0b00100,0b00100,0b00100,0b00100,0b00100,0b01110],
    'm': [0b00000,0b00000,0b11010,0b10101,0b10101,0b10001,0b10001],
    'n': [0b00000,0b00000,0b11110,0b10001,0b10001,0b10001,0b10001],
    'o': [0b00000,0b00000,0b01110,0b10001,0b10001,0b10001,0b01110],
    'p': [0b00000,0b11110,0b10001,0b10001,0b11110,0b10000,0b10000],
    'q': [0b00000,0b01111,0b10001,0b10001,0b01111,0b00001,0b00001],
    'r': [0b00000,0b00000,0b10110,0b11000,0b10000,0b10000,0b10000],
    's': [0b00000,0b00000,0b01110,0b10000,0b01110,0b00001,0b11110],
    't': [0b01000,0b01000,0b11100,0b01000,0b01000,0b01001,0b00110],
    'u': [0b00000,0b00000,0b10001,0b10001,0b10001,0b10011,0b01101],
    'v': [0b00000,0b00000,0b10001,0b10001,0b10001,0b01010,0b00100],
    'w': [0b00000,0b00000,0b10001,0b10001,0b10101,0b10101,0b01010],
    'x': [0b00000,0b00000,0b10001,0b01010,0b00100,0b01010,0b10001],
    'y': [0b00000,0b10001,0b10001,0b01111,0b00001,0b10001,0b01110],
    'z': [0b00000,0b00000,0b11111,0b00010,0b00100,0b01000,0b11111],
    '0': [0b01110,0b10001,0b10011,0b10101,0b11001,0b10001,0b01110],
    '1': [0b00100,0b01100,0b00100,0b00100,0b00100,0b00100,0b01110],
    '2': [0b01110,0b10001,0b00001,0b00110,0b01000,0b10000,0b11111],
    '3': [0b11111,0b00010,0b00100,0b00110,0b00001,0b10001,0b01110],
    '4': [0b00010,0b00110,0b01010,0b10010,0b11111,0b00010,0b00010],
    '5': [0b11111,0b10000,0b11110,0b00001,0b00001,0b10001,0b01110],
    '6': [0b00110,0b01000,0b10000,0b11110,0b10001,0b10001,0b01110],
    '7': [0b11111,0b00001,0b00010,0b00100,0b01000,0b01000,0b01000],
    '8': [0b01110,0b10001,0b10001,0b01110,0b10001,0b10001,0b01110],
    '9': [0b01110,0b10001,0b10001,0b01111,0b00001,0b00010,0b01100],
    '-': [0b00000,0b00000,0b00000,0b11111,0b00000,0b00000,0b00000],
    '.': [0b00000,0b00000,0b00000,0b00000,0b00000,0b01100,0b01100],
    ',': [0b00000,0b00000,0b00000,0b00000,0b01100,0b00100,0b01000],
    '!': [0b00100,0b00100,0b00100,0b00100,0b00100,0b00000,0b00100],
    '?': [0b01110,0b10001,0b00001,0b00110,0b00100,0b00000,0b00100],
    ':': [0b00000,0b01100,0b01100,0b00000,0b01100,0b01100,0b00000],
    '/': [0b00001,0b00010,0b00010,0b00100,0b01000,0b01000,0b10000],
    '(': [0b00010,0b00100,0b01000,0b01000,0b01000,0b00100,0b00010],
    ')': [0b01000,0b00100,0b00010,0b00010,0b00010,0b00100,0b01000],
    '_': [0b00000,0b00000,0b00000,0b00000,0b00000,0b00000,0b11111],
    "'": [0b00100,0b00100,0b00000,0b00000,0b00000,0b00000,0b00000],
    '"': [0b01010,0b01010,0b00000,0b00000,0b00000,0b00000,0b00000],
    '%': [0b11000,0b11001,0b00010,0b00100,0b01000,0b10011,0b00011],
    '+': [0b00000,0b00100,0b00100,0b11111,0b00100,0b00100,0b00000],
    '=': [0b00000,0b00000,0b11111,0b00000,0b11111,0b00000,0b00000],
    '@': [0b01110,0b10001,0b10001,0b10111,0b10101,0b10110,0b01111],
    '#': [0b01010,0b01010,0b11111,0b01010,0b11111,0b01010,0b01010],
}
_FONT_GLYPH_W = 5
_FONT_GLYPH_H = 7
_FONT_GLYPH_GAP = 1


def _draw_text_pixels(pixels, img_w, img_h, x, y, text, r, g, b, scale=1):
    """Blit text into a flat RGBA pixel array using the 5×7 bitmap font."""
    cx = x
    for ch in text:
        glyph = _FONT_5x7.get(ch, _FONT_5x7.get('?', [0]*7))
        for row_idx, row_bits in enumerate(glyph):
            py_base = y + (_FONT_GLYPH_H - 1 - row_idx) * scale
            for col in range(_FONT_GLYPH_W):
                if row_bits & (1 << (_FONT_GLYPH_W - 1 - col)):
                    px_base = cx + col * scale
                    for sy in range(scale):
                        for sx in range(scale):
                            px = px_base + sx
                            py = py_base + sy
                            if 0 <= px < img_w and 0 <= py < img_h:
                                idx = (py * img_w + px) * 4
                                pixels[idx]     = r
                                pixels[idx + 1] = g
                                pixels[idx + 2] = b
                                pixels[idx + 3] = 1.0
        cx += (_FONT_GLYPH_W + _FONT_GLYPH_GAP) * scale


def _composite_legend(render_img, classes):
    """Composite the legend onto a bpy.types.Image in-place."""
    w = render_img.size[0]
    h = render_img.size[1]

    render_pixels = list(render_img.pixels)
    legend_pixels = _build_legend_pixels(classes, w, h)

    for i in range(w * h):
        base = i * 4
        sr = legend_pixels[base]
        sg = legend_pixels[base + 1]
        sb = legend_pixels[base + 2]
        sa = legend_pixels[base + 3]
        if sa > 0.0:
            dr = render_pixels[base]
            dg = render_pixels[base + 1]
            db = render_pixels[base + 2]
            da = render_pixels[base + 3]
            out_a = sa + da * (1.0 - sa)
            if out_a > 0.0:
                render_pixels[base]     = (sr * sa + dr * da * (1.0 - sa)) / out_a
                render_pixels[base + 1] = (sg * sa + dg * da * (1.0 - sa)) / out_a
                render_pixels[base + 2] = (sb * sa + db * da * (1.0 - sa)) / out_a
                render_pixels[base + 3] = out_a

    render_img.pixels = render_pixels


class OBJECT_OT_render_uncertainty_view(bpy.types.Operator):
    """Render the current viewport with the uncertainty legend overlaid"""
    bl_idname = "object.render_uncertainty_view"
    bl_label = "Render Uncertainty View"
    bl_options = {'REGISTER'}

    filepath: bpy.props.StringProperty(
        name="File Path",
        description="Path to save the rendered image",
        subtype='FILE_PATH',
        default="uncertainty_render.png",
    )
    filter_glob: bpy.props.StringProperty(
        default="*.png;*.jpg;*.jpeg",
        options={'HIDDEN'},
    )

    def invoke(self, context, event):
        blend_path = bpy.data.filepath
        if blend_path:
            base = os.path.splitext(blend_path)[0]
            self.filepath = base + "_uncertainty_render.png"
        else:
            self.filepath = "uncertainty_render.png"
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

    def execute(self, context):
        scene   = context.scene
        classes = scene.uncertainty_classes

        if not classes:
            self.report({'WARNING'}, "No uncertainty classes defined.")
            return {'CANCELLED'}

        view3d_area   = None
        view3d_region = None
        for area in context.screen.areas:
            if area.type == 'VIEW_3D':
                view3d_area = area
                for region in area.regions:
                    if region.type == 'WINDOW':
                        view3d_region = region
                        break
                break

        if view3d_area is None:
            self.report({'ERROR'}, "No 3D viewport found.")
            return {'CANCELLED'}

        set_object_color_display(context, True)

        filepath = bpy.path.abspath(self.filepath)
        if not filepath.lower().endswith((".png", ".jpg", ".jpeg")):
            filepath += ".png"

        tmp_fd, tmp_path = tempfile.mkstemp(suffix=".png")
        os.close(tmp_fd)

        prev_filepath = scene.render.filepath
        scene.render.filepath = tmp_path

        try:
            override = context.copy()
            override['area']   = view3d_area
            override['region'] = view3d_region
            with context.temp_override(**override):
                bpy.ops.render.opengl(write_still=True)
        except Exception as e:
            scene.render.filepath = prev_filepath
            os.unlink(tmp_path)
            self.report({'ERROR'}, f"Viewport render failed: {e}")
            return {'CANCELLED'}

        scene.render.filepath = prev_filepath

        class _UC:
            def __init__(self, label, color):
                self.label = label
                self.color = color

        if scene.uncertainty_render_legend:
            img_name = "_uncertainty_render_tmp"
            if img_name in bpy.data.images:
                bpy.data.images.remove(bpy.data.images[img_name])
            render_img = bpy.data.images.load(tmp_path)
            render_img.name = img_name
            render_img.pack()

            class_snapshot = [_UC(uc.label, tuple(uc.color)) for uc in classes]
            _composite_legend(render_img, class_snapshot)

            render_img.filepath_raw = filepath
            render_img.file_format  = 'PNG'
            render_img.save_render(filepath)
            bpy.data.images.remove(render_img)
        else:
            import shutil
            shutil.copy2(tmp_path, filepath)

        try:
            os.unlink(tmp_path)
        except OSError:
            pass

        self.report({'INFO'}, f"Rendered to '{filepath}'.")
        return {'FINISHED'}


# ---------------------------------------------------------------------------
# Panel
# ---------------------------------------------------------------------------

class VIEW3D_PT_uncertainty_index(bpy.types.Panel):
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Uncertainty"
    bl_label = "Uncertainty Index"

    def draw(self, context):
        layout = self.layout
        scene = context.scene
        classes = scene.uncertainty_classes
        index = scene.uncertainty_class_index
        selected_preset = scene.uncertainty_preset_selector
        is_user_preset = selected_preset.startswith("user::")

        # --- Presets ---
        preset_box = layout.box()
        preset_box.label(text="Presets", icon='PRESET')
        preset_box.prop(scene, "uncertainty_preset_selector", text="")

        row = preset_box.row(align=True)
        row.operator("object.load_selected_preset", text="Load", icon='IMPORT')
        row.operator("object.save_user_preset", text="Save", icon='ADD')
        row.operator("object.delete_selected_preset", text="Delete", icon='TRASH')

        layout.separator()

        # --- Class list ---
        class_box = layout.box()
        class_box.label(text="Classes", icon='LINENUMBERS_ON')

        row = class_box.row()
        row.operator("object.add_uncertainty_class", icon='ADD', text="Add")
        row.operator("object.remove_uncertainty_class", icon='REMOVE', text="Remove")

        for i, uc in enumerate(classes):
            row = class_box.row(align=True)
            row.alert = (i == index)
            op = row.operator(
                "object.select_uncertainty_class",
                text="",
                icon='RADIOBUT_ON' if i == index else 'RADIOBUT_OFF'
            )
            op.class_index = i
            row.prop(uc, "label", text="")
            row.prop(uc, "color", text="")

        layout.separator()

        # --- Assign ---
        assign_box = layout.box()
        assign_box.label(text="Assign to Selection", icon='OBJECT_DATA')
        if classes and 0 <= index < len(classes):
            assign_box.label(text=f"Selected: {classes[index].label}")
        else:
            assign_box.label(text="No classes defined", icon='ERROR')
        assign_box.operator("object.assign_uncertainty", icon='BRUSH_DATA')

        layout.separator()

        # --- Viewport display ---
        display_box = layout.box()
        display_box.label(text="Viewport Display", icon='SHADING_SOLID')
        color_active = is_object_color_active(context)
        display_box.operator(
            "object.toggle_object_color_display",
            text="Object Color: On" if color_active else "Object Color: Off",
            icon='HIDE_OFF' if color_active else 'HIDE_ON',
            depress=color_active,
        )

        layout.separator()

        # --- Active object info ---
        obj = context.active_object
        info_box = layout.box()
        info_box.label(text="Active Object", icon='INFO')
        if obj:
            label = obj.get("uncertainty_label", None)
            if label is not None:
                info_box.label(text=f"Current: {label}")
            else:
                info_box.label(text="No uncertainty assigned yet")
        else:
            info_box.label(text="No active object")

        layout.separator()

        # --- Statistics (collapsible) ---
        stats_box = layout.box()
        stats_row = stats_box.row()
        stats_open = bool(getattr(scene, "uncertainty_ui_stats_open", False))
        stats_row.prop(
            scene,
            "uncertainty_ui_stats_open",
            text="",
            emboss=False,
            icon='TRIA_DOWN' if stats_open else 'TRIA_RIGHT',
        )
        stats_row.label(text="Statistics", icon='SORTSIZE')

        if stats_open:
            counts = {}
            total_assigned = 0
            mesh_objects = [o for o in bpy.data.objects if o.type == 'MESH']
            for obj in mesh_objects:
                idx = obj.get("uncertainty_index", None)
                if idx is not None:
                    counts[idx] = counts.get(idx, 0) + 1
                    total_assigned += 1

            if total_assigned == 0 or not classes:
                stats_box.label(text="No assignments yet", icon='INFO')
            else:
                for i, uc in enumerate(classes):
                    count = counts.get(i, 0)
                    pct = (count / total_assigned * 100) if total_assigned > 0 else 0
                    split = stats_box.split(factor=0.55)
                    split.label(text=uc.label)
                    split.label(text=f"{count} obj  ({pct:.1f}%)")
                stats_box.separator()
                stats_box.label(text=f"Total assigned: {total_assigned} of {len(mesh_objects)} meshes")

        layout.separator()

        # --- Export ---
        export_box = layout.box()
        export_box.label(text="Export", icon='EXPORT')
        export_box.operator("object.render_uncertainty_view", icon='RENDER_STILL')
        export_box.prop(scene, "uncertainty_render_legend")
        export_box.operator("object.export_uncertainty_csv", icon='FILE_TEXT')


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

CLASSES = [
    UncertaintyClass,
    OBJECT_OT_add_uncertainty_class,
    OBJECT_OT_remove_uncertainty_class,
    OBJECT_OT_select_uncertainty_class,
    OBJECT_OT_assign_uncertainty_index,
    OBJECT_OT_load_selected_preset,
    OBJECT_OT_save_user_preset,
    OBJECT_OT_delete_selected_preset,
    OBJECT_OT_toggle_object_color_display,
    OBJECT_OT_export_uncertainty_csv,
    OBJECT_OT_render_uncertainty_view,
    VIEW3D_PT_uncertainty_index,
]

def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)

    bpy.types.Scene.uncertainty_classes = bpy.props.CollectionProperty(type=UncertaintyClass)
    bpy.types.Scene.uncertainty_class_index = bpy.props.IntProperty(name="Selected Class", default=0)
    bpy.types.Scene.uncertainty_preset_selector = bpy.props.EnumProperty(
        name="Preset",
        description="Select a preset to load",
        items=preset_items_callback,
    )
    bpy.types.Scene.uncertainty_ui_stats_open = bpy.props.BoolProperty(
        name="Statistics Open",
        default=False,
    )
    bpy.types.Scene.uncertainty_render_legend = bpy.props.BoolProperty(
        name="Include Legend",
        description="Composite the uncertainty legend onto the rendered image",
        default=True,
    )

def unregister():
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)

    del bpy.types.Scene.uncertainty_classes
    del bpy.types.Scene.uncertainty_class_index
    del bpy.types.Scene.uncertainty_preset_selector
    del bpy.types.Scene.uncertainty_ui_stats_open
    del bpy.types.Scene.uncertainty_render_legend

if __name__ == "__main__":
    register()