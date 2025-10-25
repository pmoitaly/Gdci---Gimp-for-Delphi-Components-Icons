#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MIT License

Copyright (c) 2025 Paolo Morandotti

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
----------------------------------------------------------------------------------------
Export Component Icons (GIMP 3.0.6) - No PDB approach - Optimized + RC generation
- Duplicate only twice per component (one master for BMP, one for PNG).
- For each master: merge/flatten once, then scale->save->restore for each size.
- New menu entry: generate .rc files (one .rc per component) referencing PNG names like TMyComponent16.png
"""
import os
import sys
import traceback
import re
import gi

gi.require_version("Gimp", "3.0")
gi.require_version("GimpUi", "3.0")
gi.require_version("Gtk", "3.0")
gi.require_version("Gio", "2.0")

from gi.repository import Gimp
from gi.repository import GimpUi
from gi.repository import Gegl
from gi.repository import Gtk
from gi.repository import Gio

# plugin procedure names
plug_in_proc = "pl-export-delphi-icons"
plug_in_proc_make_rc = "pl-export-delphi-icons-make-rc"
plug_in_binary = "py3-pl-export-delphi-icons"

# Export sizes (requested)
EXPORT_SIZES = [24, 32, 48, 72, 96, 128, 256, 512, 1024]


# -------------------------
# UI utilities (GTK3)
# -------------------------
def _ensure_ui_initialized():
    try:
        GimpUi.init("export_component_icons_no_pdb")
    except Exception:
        pass


def ask_output_folder(default_folder=None):
    _ensure_ui_initialized()

    dialog = Gtk.FileChooserDialog(
        title="Select Output Folder",
        parent=None,
        action=Gtk.FileChooserAction.SELECT_FOLDER,
    )
    dialog.add_buttons(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
                       Gtk.STOCK_OPEN, Gtk.ResponseType.OK)

    if default_folder:
        try:
            dialog.set_current_folder(default_folder)
        except Exception:
            pass

    try:
        response = dialog.run()
    except Exception:
        dialog.destroy()
        return None

    selected_folder = None
    if response == Gtk.ResponseType.OK:
        try:
            selected_folder = dialog.get_filename()
        except Exception:
            selected_folder = None

    dialog.destroy()

    if not selected_folder or (isinstance(selected_folder, str) and selected_folder.strip() == ""):
        return None
    return selected_folder


def show_message_dialog(message_text, title="Information", image=None, run_mode=None):
    if run_mode is not None and run_mode != Gimp.RunMode.INTERACTIVE:
        return None

    _ensure_ui_initialized()

    dialog = Gtk.MessageDialog(
        parent=None,
        flags=Gtk.DialogFlags.MODAL,
        type=Gtk.MessageType.INFO,
        buttons=Gtk.ButtonsType.OK,
        message_format=message_text
    )
    dialog.set_title(title)
    dialog.set_default_size(360, 120)

    try:
        if image is not None and hasattr(GimpUi, "get_window_for_image"):
            parent = None
            try:
                parent = GimpUi.get_window_for_image(image)
            except Exception:
                parent = None
            if parent:
                try:
                    dialog.set_transient_for(parent)
                except Exception:
                    pass
    except Exception:
        pass

    try:
        dialog.show_all()
        response = dialog.run()
    except Exception:
        response = Gtk.ResponseType.OK
    finally:
        dialog.destroy()

    return True if response == Gtk.ResponseType.OK else None


# -------------------------
# Image / export utilities (no PDB)
# -------------------------
def _safe_msg(msg):
    try:
        Gimp.message(str(msg))
    except Exception:
        try:
            print(str(msg), file=sys.stderr)
        except Exception:
            pass


def find_layer_by_name(image, name):
    try:
        for l in image.get_layers():
            if l.get_name() == name:
                return l
    except Exception:
        pass
    return None


def is_component_layer(layer):
    try:
        return layer.get_name().startswith("Cmp ")
    except Exception:
        return False


def duplicate_image(image):
    try:
        if hasattr(image, "duplicate"):
            return image.duplicate()
    except Exception as e:
        _safe_msg(f"duplicate_image: image.duplicate failed: {e}")
    raise RuntimeError("Image duplication not available")


def merge_visible_to_single_layer(image):
    try:
        if hasattr(image, "merge_visible_layers"):
            try:
                merged = image.merge_visible_layers()
                return merged
            except TypeError:
                pass
            except Exception as e:
                _safe_msg(f"merge_visible_layers() raised: {e}")
    except Exception:
        pass

    def try_getattr_chain(root, *names):
        obj = root
        try:
            for n in names:
                obj = getattr(obj, n)
            return obj
        except Exception:
            return None

    enum_value = try_getattr_chain(Gimp, "ImageMergeType", "CLIP_TO_IMAGE") or \
                 try_getattr_chain(Gimp, "MergeType", "CLIP_TO_IMAGE") or \
                 try_getattr_chain(Gimp, "Image", "MergeType", "CLIP_TO_IMAGE") or \
                 try_getattr_chain(Gimp, "ImageMergeType")

    if enum_value is None:
        for cand in dir(Gimp):
            if cand.lower().find("merge") != -1:
                try:
                    obj = getattr(Gimp, cand)
                except Exception:
                    continue
                for sub in ("CLIP_TO_IMAGE", "CLIP", "TO_IMAGE", "CLIP_TO"):
                    if hasattr(obj, sub):
                        enum_value = getattr(obj, sub)
                        break
            if enum_value is not None:
                break

    if enum_value is not None:
        try:
            merged = image.merge_visible_layers(enum_value)
            return merged
        except Exception as e:
            _safe_msg(f"merge_visible_layers(enum) failed: {e}")

    for iv in (0, 1, 2):
        try:
            merged = image.merge_visible_layers(iv)
            return merged
        except Exception:
            pass

    try:
        layers = image.get_layers()
        visible_layers = [l for l in layers if getattr(l, "get_visible", lambda: True)()]
        if visible_layers:
            _safe_msg("merge_visible_to_single_layer: falling back to first visible layer")
            return visible_layers[0]
    except Exception:
        pass

    raise RuntimeError("Unable to merge visible layers on this GIMP build.")


def scale_image(image, width, height):
    try:
        if hasattr(image, "scale"):
            image.scale(width, height)
            return
    except Exception as e:
        _safe_msg(f"scale_image: image.scale failed: {e}")
    raise RuntimeError("Image scaling not available")


def flatten_image_if_possible(image):
    try:
        if hasattr(image, "flatten"):
            flat = image.flatten()
            return flat
    except Exception as e:
        _safe_msg(f"flatten failed: {e}")
    try:
        layers = image.get_layers()
        if layers:
            return layers[0]
    except Exception:
        pass
    return None


def delete_image_safe(image):
    try:
        if hasattr(image, "delete"):
            image.delete()
            return
    except Exception:
        pass


def gimp_file_save(image, outpath):
    try:
        gfile = None
        try:
            gfile = Gio.File.new_for_path(outpath)
        except Exception as e:
            _safe_msg(f"Gio.File.new_for_path failed for {outpath}: {e}")
            try:
                gfile = Gio.File.new_for_uri("file://" + outpath)
            except Exception:
                gfile = None

        if gfile is None:
            raise RuntimeError("Cannot build Gio.File for " + outpath)

        try:
            res = Gimp.file_save(Gimp.RunMode.NONINTERACTIVE, image, gfile, None)
            return bool(res)
        except Exception as e:
            _safe_msg(f"Gimp.file_save attempt failed: {e}")
            try:
                res2 = Gimp.file_save(Gimp.RunMode.NONINTERACTIVE, image, gfile, None)
                return bool(res2)
            except Exception as e2:
                _safe_msg(f"Gimp.file_save second attempt failed: {e2}")
                return False
    except Exception as e:
        _safe_msg(f"gimp_file_save error for {outpath}: {e}\n{traceback.format_exc()}")
        return False


# -------------------------
# NEW: helper to get image dimensions safely
# -------------------------
def get_image_size_safe(image):
    try:
        if hasattr(image, "get_width") and hasattr(image, "get_height"):
            return (image.get_width(), image.get_height())
        if hasattr(image, "width") and hasattr(image, "height"):
            return (int(image.width), int(image.height))
    except Exception:
        pass
    return (1024, 1024)


# -------------------------
# Main export function (optimized)
# -------------------------
def export_component_variants_no_pdb(procedure, runMode, image, nDrawables, args, data):
    outputFolder = None
    try:
        if runMode != Gimp.RunMode.INTERACTIVE:
            try:
                if args and len(args) > 0:
                    outputFolder = str(args[0])
            except Exception:
                outputFolder = None
    except Exception:
        outputFolder = None

    if runMode == Gimp.RunMode.INTERACTIVE:
        outputFolder = ask_output_folder(default_folder=outputFolder or os.path.expanduser("~"))

    if not outputFolder or (isinstance(outputFolder, str) and outputFolder.strip() == ""):
        if runMode == Gimp.RunMode.INTERACTIVE:
            show_message_dialog("Export operation canceled by the user.", "Operation canceled", image=image, run_mode=runMode)
        return procedure.new_return_values(Gimp.PDBStatusType.CANCEL, None)

    try:
        os.makedirs(outputFolder, exist_ok=True)
    except Exception as e:
        show_message_dialog(f"Cannot create output folder: {outputFolder}\nError: {e}", "Error", image=image, run_mode=runMode)
        return procedure.new_return_values(Gimp.PDBStatusType.CALLING_ERROR, None)

    layerTransparent = find_layer_by_name(image, "Transparent Background")
    layerFucsia = find_layer_by_name(image, "Fucsia Background")
    layerSmallLogo = find_layer_by_name(image, "Small logo")

    if layerSmallLogo is None:
        _safe_msg("Warning: 'Small logo' layer not found.")
    if layerFucsia is None:
        _safe_msg("Warning: 'Fucsia Background' layer not found.")
    if layerTransparent is None:
        _safe_msg("Warning: 'Transparent Background' layer not found.")

    try:
        allLayers = image.get_layers()
        componentLayers = [l for l in allLayers if is_component_layer(l)]
    except Exception:
        componentLayers = []

    if not componentLayers:
        show_message_dialog("No component layers found (names starting with 'Cmp ').", "No components", image=image, run_mode=runMode)
        return procedure.new_return_values(Gimp.PDBStatusType.CALLING_ERROR, None)

    # iterate components
    for compLayer in componentLayers:
        compSafe = re.sub(r'[^A-Za-z0-9_]', '_', compLayer.get_name().split(None, 1)[1].strip()) if compLayer.get_name().lower().startswith("cmp ") else re.sub(r'[^A-Za-z0-9_]', '_', compLayer.get_name())

        # hide all component layers
        try:
            for l in componentLayers:
                try:
                    l.set_visible(False)
                except Exception:
                    pass
        except Exception:
            pass

        # show small logo and this comp
        try:
            if layerSmallLogo is not None:
                layerSmallLogo.set_visible(True)
        except Exception:
            pass
        try:
            compLayer.set_visible(True)
        except Exception:
            pass

        # ------- BMP master (duplicate once, merge/flatten once) -------
        bmp_master = None
        try:
            if layerFucsia is not None:
                try:
                    layerFucsia.set_visible(True)
                except Exception:
                    pass
            if layerTransparent is not None:
                try:
                    layerTransparent.set_visible(False)
                except Exception:
                    pass

            bmp_master = duplicate_image(image)
            mergedBmp = merge_visible_to_single_layer(bmp_master)
            # prefer flatten for BMP (to remove alpha)
            bmp_drawable = None
            try:
                bmp_drawable = flatten_image_if_possible(bmp_master)
            except Exception:
                bmp_drawable = mergedBmp

            # record original size to restore after each scale
            orig_w, orig_h = get_image_size_safe(bmp_master)

            # for each size: scale -> save -> restore
            for s in EXPORT_SIZES:
                outPath = os.path.join(outputFolder, f"{compSafe}{s}.bmp")
                try:
                    try:
                        scale_image(bmp_master, s, s)
                    except Exception as se:
                        _safe_msg(f"BMP scale failed for {s}: {se}")
                    ok = gimp_file_save(bmp_master, outPath)
                    if not ok:
                        _safe_msg(f"BMP export failed (report) for {outPath}")
                except Exception as e:
                    _safe_msg(f"Error exporting BMP {outPath}: {e}\n{traceback.format_exc()}")
                finally:
                    # restore size for next iteration
                    try:
                        scale_image(bmp_master, orig_w, orig_h)
                    except Exception:
                        # if restore fails, try to delete and recreate master to be safe
                        try:
                            delete_image_safe(bmp_master)
                        except Exception:
                            pass
                        bmp_master = duplicate_image(image)
                        mergedBmp = merge_visible_to_single_layer(bmp_master)
                        try:
                            bmp_drawable = flatten_image_if_possible(bmp_master)
                        except Exception:
                            bmp_drawable = mergedBmp
                        orig_w, orig_h = get_image_size_safe(bmp_master)
        except Exception as e:
            _safe_msg(f"Error preparing BMP master for {compLayer.get_name()}: {e}\n{traceback.format_exc()}")
        finally:
            if bmp_master is not None:
                try:
                    delete_image_safe(bmp_master)
                except Exception:
                    pass

        # ------- PNG master (duplicate once, merge once) -------
        png_master = None
        try:
            # hide fucsia, show transparent
            try:
                if layerFucsia is not None:
                    layerFucsia.set_visible(False)
            except Exception:
                pass
            try:
                if layerTransparent is not None:
                    layerTransparent.set_visible(True)
            except Exception:
                pass

            png_master = duplicate_image(image)
            mergedPng = merge_visible_to_single_layer(png_master)
            png_drawable = mergedPng

            orig_w, orig_h = get_image_size_safe(png_master)

            for s in EXPORT_SIZES:
                outPath = os.path.join(outputFolder, f"{compSafe}{s}.png")
                try:
                    try:
                        scale_image(png_master, s, s)
                    except Exception as se:
                        _safe_msg(f"PNG scale failed for {s}: {se}")
                    ok = gimp_file_save(png_master, outPath)
                    if not ok:
                        _safe_msg(f"PNG export failed (report) for {outPath}")
                except Exception as e:
                    _safe_msg(f"Error exporting PNG {outPath}: {e}\n{traceback.format_exc()}")
                finally:
                    try:
                        scale_image(png_master, orig_w, orig_h)
                    except Exception:
                        try:
                            delete_image_safe(png_master)
                        except Exception:
                            pass
                        png_master = duplicate_image(image)
                        mergedPng = merge_visible_to_single_layer(png_master)
                        png_drawable = mergedPng
                        orig_w, orig_h = get_image_size_safe(png_master)
        except Exception as e:
            _safe_msg(f"Error preparing PNG master for {compLayer.get_name()}: {e}\n{traceback.format_exc()}")
        finally:
            if png_master is not None:
                try:
                    delete_image_safe(png_master)
                except Exception:
                    pass

    _safe_msg(f"Export completed. Files saved into: {outputFolder}")
    return procedure.new_return_values(Gimp.PDBStatusType.SUCCESS, None)


# -------------------------
# NEW: generate .rc files per component
# -------------------------
def generate_rc_files(procedure, runMode, image, nDrawables, args, data):
    outFolder = None
    try:
        if runMode != Gimp.RunMode.INTERACTIVE:
            try:
                if args and len(args) > 0:
                    outFolder = str(args[0])
            except Exception:
                outFolder = None
    except Exception:
        outFolder = None

    if runMode == Gimp.RunMode.INTERACTIVE:
        outFolder = ask_output_folder(default_folder=outFolder or os.path.expanduser("~"))

    if not outFolder or (isinstance(outFolder, str) and outFolder.strip() == ""):
        if runMode == Gimp.RunMode.INTERACTIVE:
            show_message_dialog("Operation canceled by the user.", "Canceled", image=image, run_mode=runMode)
        return procedure.new_return_values(Gimp.PDBStatusType.CANCEL, None)

    try:
        os.makedirs(outFolder, exist_ok=True)
    except Exception as e:
        show_message_dialog(f"Cannot create output folder: {outFolder}\nError: {e}", "Error", image=image, run_mode=runMode)
        return procedure.new_return_values(Gimp.PDBStatusType.CALLING_ERROR, None)

    # sizes include 16 plus EXPORT_SIZES, unique and sorted
    sizes = sorted(set([16] + list(EXPORT_SIZES)))

    try:
        all_layers = image.get_layers()
        component_layers = [l for l in all_layers if is_component_layer(l)]
    except Exception:
        component_layers = []

    if not component_layers:
        show_message_dialog("No component layers found (names starting with 'Cmp ').", "No components", image=image, run_mode=runMode)
        return procedure.new_return_values(Gimp.PDBStatusType.CALLING_ERROR, None)

    created_files = []
    for layer in component_layers:
        try:
            raw = layer.get_name()
            if raw.lower().startswith("cmp "):
                name = raw.split(None, 1)[1].strip()
            else:
                name = raw.strip()
        except Exception:
            continue

        # identifier sanitization
        ident = re.sub(r'[^A-Za-z0-9_]', '_', name)
        resource_base = ident

        rc_filename = os.path.join(outFolder, f"{resource_base}.rc")
        try:
            with open(rc_filename, "w", encoding="utf-8") as fh:
                fh.write("// Generated by export plugin\n")
                fh.write(f"// Component: {name}\n")
                for s in sizes:
                    res_name = f"{resource_base}{s}_PNG"
                    png_fname = f"{resource_base}{s}.png"
                    fh.write(f"{res_name} RCDATA \"{png_fname}\"\n")
            created_files.append(rc_filename)
        except Exception as e:
            _safe_msg(f"Failed to write {rc_filename}: {e}")

    if created_files:
        msg = "Created .rc files:\n" + "\n".join(created_files)
        show_message_dialog(msg, "RC files created", image=image, run_mode=runMode)
        return procedure.new_return_values(Gimp.PDBStatusType.SUCCESS, None)
    else:
        show_message_dialog("No .rc files were created (errors).", "Failed", image=image, run_mode=runMode)
        return procedure.new_return_values(Gimp.PDBStatusType.CALLING_ERROR, None)

# -------------------------
# NEW: create a template image with required layers
# -------------------------
def create_template_image(procedure, runMode, image, nDrawables, args, data):
    """
    Create a new 1024x1024 template image with:
      - Transparent Background (layer)
      - Fucsia Background (layer filled with #ff00ff)
      - Small logo (transparent layer with white rectangle at (8,8) size 84x84)
      - Copy and rename as Cmp TMyComponent (transparent empty layer)
    The function tries multiple strategies to fill the fuchsia background robustly.
    """

    old_background = Gimp.context_get_background()
    fucsia = Gegl.Color()
    fucsia.set_rgba(1, 0, 1, 1.0)
    white = Gegl.Color()
    white.set_rgba(1, 1, 1, 1.0)

    try:
        # create image (RGB with alpha)
        try:
            new_img = Gimp.Image.new(1024, 1024, Gimp.ImageBaseType.RGB)
        except Exception as E:
            new_img = Gimp.Image.new(1024, 1024, 0)

        # helper: create RGBA layer (common GI signature)
        def _new_rgba_layer(img, name, w=None, h=None):
            if w is None:
                try:
                    w = img.get_width()
                except Exception:
                    w = 1024
            if h is None:
                try:
                    h = img.get_height()
                except Exception:
                    h = 1024
            try:
                # common signature: (image, name, width, height, ImageType.RGBA_IMAGE, opacity, LayerMode)
                layer = Gimp.Layer.new(img, name, w, h, Gimp.ImageType.RGBA_IMAGE, 100.0, Gimp.LayerMode.NORMAL)
            except Exception as e:
                # try alternate ordering (rare)
                try:
                    layer = Gimp.Layer.new(img, name, w, h, Gimp.ImageType.RGBA_IMAGE, 100.0, Gimp.LayerMode.NORMAL)
                except Exception as e2:
                    raise RuntimeError(f"Unable to create RGBA layer: {e} / {e2}")
            # insert at top
            try:
                img.insert_layer(layer, None, 0)
            except Exception:
                try:
                    img.add_layer(layer, 0)
                except Exception:
                    pass
            return layer

        # Transparent Background layer (full-size RGBA)
        tb_layer = _new_rgba_layer(new_img, "Transparent Background")
        tb_layer.fill(Gimp.FillType.TRANSPARENT)
        tb_layer.set_visible(False)
           
        # Fucsia Background (full-size RGBA)
        fb_layer = _new_rgba_layer(new_img, "Fucsia Background")
        Gimp.context_set_background(fucsia)
        fb_layer.fill(Gimp.FillType.BACKGROUND)
        Gimp.context_set_background(old_background)
        fb_layer.set_visible(False)

        # Small logo: create a full-size transparent layer that will contain the white rect
        sl_layer = _new_rgba_layer(new_img, "Small logo")

        # Create temporary small white layer (500x300), offset to (8,8), then merge into small_layer
        try:
            tmp_rect = Gimp.Layer.new(new_img, "tmp_white_rect", 500, 300, Gimp.ImageType.RGBA_IMAGE, 100.0, Gimp.LayerMode.NORMAL)
            new_img.insert_layer(tmp_rect, None, 0)
            tmp_rect.fill(Gimp.FillType.WHITE)
            tmp_rect.set_offsets(8, 8)
            # ensure sl_layer and tmp_rect visible
            tmp_rect.set_visible(True)
            sl_layer.set_visible(True)
            # Merge visible layers so the white rect ends up inside "Small logo"
            merged = new_img.merge_visible_layers(0)
            if merged:
                merged.set_name("Small logo")

        except Exception:
            # if tmp rect creation failed, leave small_layer empty
            pass

        # Component placeholder layer (transparent)
        dp_layer = _new_rgba_layer(new_img, "Duplicate and rename as Cmp TMyComponent")
        
        tb_layer.set_visible(True)

        # show the image in a display
        try:
            Gimp.Display.new(new_img)
        except Exception:
            try:
                GimpUi.display_image(new_img)
            except Exception:
                pass

        show_message_dialog("Template image created (1024x1024) with required layers.", "Template created", image=new_img, run_mode=runMode)
        return procedure.new_return_values(Gimp.PDBStatusType.SUCCESS, None)

    except Exception as err:
        _safe_msg(f"create_template_image failed: {err}\n{traceback.format_exc()}")
        show_message_dialog(f"Error creating template image:\n{err}", "Error")
        return procedure.new_return_values(Gimp.PDBStatusType.CALLING_ERROR, None)

# Register the new procedure in the plugin registration
# add plug_in_proc_create_template = "pl-export-delphi-icons-create-template"
plug_in_proc_create_template = "pl-export-delphi-icons-create-template"


# -------------------------
# Register both procedures with GIMP
# -------------------------
class ExportComponentIconsPlugIn(Gimp.PlugIn):
    def do_query_procedures(self):
        return [plug_in_proc, plug_in_proc_make_rc, plug_in_proc_create_template]

    def do_create_procedure(self, name):
        
        image_menu_path = '<Image>/_Pl Plugin For Delphi/'

        if name == plug_in_proc:
            proc = Gimp.ImageProcedure.new(self, name, Gimp.PDBProcType.PLUGIN, export_component_variants_no_pdb, None)
            proc.set_image_types("*")
            proc.set_menu_label("_Export Delphi icons...")
            proc.add_menu_path(image_menu_path)
            proc.set_documentation(
                "Export component icons (BMP with Fucsia Background, PNG with Transparent Background) at multiple sizes.",
                "Iterates layers named 'Cmp ...' showing each with 'Small logo' and exporting BMP/PNG variants.",
                name
            )
            proc.set_attribution("Paolo Morandotti", "Copyright Paolo Morandotti 2025 - Released under MIT Licence", "plcIconsExporter")
            return proc
        elif name == plug_in_proc_make_rc:
            proc = Gimp.ImageProcedure.new(self, name, Gimp.PDBProcType.PLUGIN, generate_rc_files, None)
            proc.set_image_types("*")
            proc.set_menu_label("Generate _RC for Components...")
            proc.add_menu_path(image_menu_path)
            proc.set_documentation(
                "Generate .rc files for components (used to build .res).",
                "Creates one .rc file per component naming PNG resources for multiple sizes.",
                name
            )
            proc.set_attribution("Paolo Morandotti", "Copyright Paolo Morandotti 2025 - Released under MIT Licence", "plcIconsExporter")
            return proc
        elif name == plug_in_proc_create_template:
            proc = Gimp.ImageProcedure.new(self, name, Gimp.PDBProcType.PLUGIN, create_template_image, None)
            proc.set_menu_label("Create _Icons template")
            proc.add_menu_path(image_menu_path)
            proc.set_documentation(
                "Create a new 1024x1024 template image with the layers required by the exporter.",
                "Creates a new image with Transparent Background, Fucsia Background, Small logo and a component placeholder layer.",
                name
            )
            proc.set_sensitivity_mask(Gimp.ProcedureSensitivityMask.ALWAYS)
            proc.set_attribution("Paolo Morandotti", "Copyright Paolo Morandotti 2025 - Released under MIT Licence", "plcIconsExporter")
            return proc
        else:
            return None


Gimp.main(ExportComponentIconsPlugIn.__gtype__, sys.argv)
