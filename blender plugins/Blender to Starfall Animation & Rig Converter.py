bl_info = {
    "name": "Blender to Starfall Animation & Rig Converter",
    "author": "Nakkitsunami",
    "version": (1, 3),
    "blender": (2, 80, 0),
    "location": "3D View > Object > Export Slashblade Anim / Armature Properties",
    "description": "Export animation keyframes to anim/*.txt & bones/rig to rig/*.txt",
    "category": "Export",
}

import bpy
import os
import math
from mathutils import Matrix
from mathutils import Euler
from math import radians

# --- Utilities ---
def ensure_dir(path):
    if not os.path.exists(path):
        os.makedirs(path, exist_ok=True)

def vec_to_angle_str(deg_ang):
    return "Angle({:.6f},{:.6f},{:.6f})".format(deg_ang[0], deg_ang[1], deg_ang[2])
    
def vec_to_str(vec):
    return "Vector({:.6f},{:.6f},{:.6f})".format(vec[0], vec[1], vec[2])
    
def tuple_to_angle(deg_tuple):
    return Euler((math.radians(deg_tuple[0]), math.radians(deg_tuple[1]), math.radians(deg_tuple[2])), 'XYZ')

def tuple_to_angle_degree(deg_tuple):
    return Euler((math.degrees(deg_tuple[0]), math.degrees(deg_tuple[1]), math.degrees(deg_tuple[2])), 'XYZ')

def gather_action_keyframes(action):
    frames = set()
    for fcu in action.fcurves:
        for kp in fcu.keyframe_points:
            frames.add(int(round(kp.co.x)))
    return sorted(frames)

def pose_bone_relative_euler_degrees(arm_obj, bone):
    # Torso (root) bone — world space
    if bone.parent is None:
        rel_matrix = bone.matrix
        rotation = 90
    else:
        rel_matrix = bone.parent.matrix.inverted() @ bone.matrix
        rotation = 0

    # Convert to ZXY Euler to match in-game convention
    euler = rel_matrix.to_euler('ZXY')
    
    # Convert to degrees
    
    return (
        math.degrees(euler.x) - rotation,
        math.degrees(euler.y),
        math.degrees(euler.z)
    )

def pose_bone_relative_vector_position(arm_obj, bone):
    # Torso (root) bone — world space
    if bone.parent is None:
        rel_matrix = bone.matrix
    else:
        rel_matrix = bone.parent.matrix.inverted() @ bone.matrix
    
    rel_pos = rel_matrix.to_translation()
    return (
        rel_pos.z*52.46,
        rel_pos.x*52.46,
        rel_pos.y*52.46
    )

# --- Export core ---
def export_rig_to_starfall_text(context, arm_obj, out_path):
    """Export armature bones to Starfall rig definition format."""
    scene = context.scene
    orig_frame = scene.frame_current


    project_name = bpy.path.basename(bpy.context.blend_data.filepath)
    project_name_no_extension = project_name.replace(".blend", "")
    project_name_lower = project_name_no_extension.lower().replace(" ", "_")

    header = f"--@name {project_name_lower}\n"
    lines = [header]
    lines.append("--@include nakilibs/pac_to_holo_loader.txt\n")
    lines.append("--@client\n\n")
    
    lines.append("require(\"nakilibs/pac_to_holo_loader.txt\")\n\n")
    
    lines.append("local bones, reftable, holos, ht, hc = {}, {}, {}, {}, 0\n")
    lines.append("local parent = chip()\n")

    lines.append("local size = 1\n\n")

    lines.append("local showBones = true\n\n")

    lines.append("local no_mat = false\n\n")
    
    lines.append("// values are converted from meters to units, x*52.46, run x/52.46 to get original values!\n\n")
    
    def format_vec(v):
        return "Vector({:.6f},{:.6f},{:.6f})".format(v.z*52.46, v.x*52.46, v.y*52.46)
    
    def write_bone(bone):
        nonlocal lines
        bone_name = bone.name
        parent_name = bone.parent.name if bone.parent else "none"
        pos = bone.head_local
        ang = tuple_to_angle_degree(bone.matrix_local.to_euler())
        if bone.parent is None:
            ang[0] = ang[0] - 90
        
        line = (
            f"hc=hc+1 ht[hc]={{hc,"
            f"parent,"
            f"reftable[\"{parent_name}\"],"
            f"{format_vec(pos)},"
            f"{vec_to_angle_str(ang)}}}\n"
            f"reftable[\"{bone_name}\"]=hc\n\n"
        )
        lines.append(line)
        for child in bone.children:
            write_bone(child)

    # Write root bones first, then recurse
    for bone in arm_obj.data.bones:
        if not bone.parent:
            write_bone(bone)
    
    
    lines.append("\n\n")
    
    lines.append("pthl.createHolos(hc,ht,no_mat,size,showBones)\n\n")
    
    
    lines.append("local bones_transfer = {}\n")
    lines.append("local bones = reftable\n")
    lines.append("hook.add(\"think\",\"initialize\",function()\n")
    lines.append("    if pthl.ready then\n")
    lines.append("        for k, v in pairs(bones) do\n")
    lines.append("            bones_transfer[v] = pthl.holos[v]\n")
    lines.append("        end\n")
    lines.append("        bones = table.copy(bones_transfer)\n")
    lines.append("        bones_transfer = nil\n")
    lines.append("        hook.remove(\"think\",\"initialize\")\n")
    lines.append("    end\n")
    lines.append("end)\n")
    
    ensure_dir(os.path.dirname(out_path))
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.writelines(lines)

    scene.frame_set(orig_frame)
    bpy.context.view_layer.update()

    return out_path

def export_action_to_starfall_text(context, arm_obj, action, out_path):
    scene = context.scene
    keyframes = gather_action_keyframes(action)
    if not keyframes:
        raise RuntimeError("No keyframes found in action!")

    project_name = bpy.path.basename(bpy.context.blend_data.filepath)
    project_name_no_extension = project_name.replace(".blend", "")
    project_name_lower = project_name_no_extension.lower().replace(" ", "_")

    anim_name = action.name
    anim_name_lower = anim_name.lower().replace(" ", "_")
    anim_name_upper = anim_name.upper().replace(" ", "_")

    header = f"--@name {project_name_lower}/anim/{anim_name_lower}\n{anim_name_upper}={{\n"
    lines = [header]

    orig_frame = scene.frame_current

    # ------------------------------------------------------------
    # AUTO-DETECT BONE ORDER
    # ------------------------------------------------------------
    # We’ll traverse the armature’s hierarchy to get consistent order.
    # (Root bones first, then children in hierarchy order)
    def collect_bones_recursive(bone, lst):
        lst.append(bone)
        for child in bone.children:
            collect_bones_recursive(child, lst)

    all_bones = []
    for bone in arm_obj.data.bones:
        if not bone.parent:
            collect_bones_recursive(bone, all_bones)

    bone_order = [b.name for b in all_bones]
    print(f"[Starfall Export] Bone order ({len(bone_order)} bones): {bone_order}")

    # ------------------------------------------------------------
    # EXPORT EACH FRAME
    # ------------------------------------------------------------
    for i, f in enumerate(keyframes):
        scene.frame_set(f)
        bpy.context.view_layer.update()

        # Determine frame length based on next keyframe
        if i < len(keyframes) - 1:
            frame_length = keyframes[i + 1] - f
        else:
            frame_length = 1  # fallback for last key

        frame_rate_modifier = 50  # Default rate mod (you can expose this later if needed)

        # Collect all bone angles in hierarchical order
        angle_lines = []
        for bone_name in bone_order:
            try:
                pb = arm_obj.pose.bones[bone_name]
                degs = pose_bone_relative_euler_degrees(arm_obj, pb)
                angle_lines.append(f"{vec_to_angle_str(degs)}, -- {bone_name}")
            except KeyError:
                angle_lines.append("Angle(0,0,0)")
        
        position_lines = []
        for bone_name in bone_order:
            try:
                pb = arm_obj.pose.bones[bone_name]
                vec = pose_bone_relative_vector_position(arm_obj, pb)
                position_lines.append(f"{vec_to_str(vec)},")
            except KeyError:
                position_lines.append("Vector(0,0,0)")
        
        # Frame block start
        lines.append("{\n")

        # Bone angles table
        lines.append("    {\n")
        for ang in angle_lines:
            lines.append(f"        {ang}\n")
        lines.append("    },\n")
        
        lines.append("    {\n")
        for pos in position_lines:
            lines.append(f"        {pos}\n")
        lines.append("    },\n")
        
        # Frame data table
        lines.append("    {\n")
        lines.append(f"        {frame_length},\n")
        lines.append(f"        {frame_rate_modifier}\n")
        lines.append("    }\n")

        # End frame
        if i < len(keyframes) - 1:
            lines.append("},\n")
        else:
            lines.append("}\n")

    lines.append("}\n")

    ensure_dir(os.path.dirname(out_path))
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.writelines(lines)

    scene.frame_set(orig_frame)
    bpy.context.view_layer.update()

    return out_path

# --- Operator & Panel ---

class STARFALL_OT_export_rig(bpy.types.Operator):
    bl_idname = "export.starfall_rig"
    bl_label = "Export Rig (.txt)"
    bl_description = "Export armature bone hierarchy and transforms for Starfall"
    bl_options = {'REGISTER'}

    def execute(self, context):
        obj = context.active_object
        if not obj or obj.type != 'ARMATURE':
            self.report({'ERROR'}, "Select an Armature object.")
            return {'CANCELLED'}

        if not bpy.data.is_saved:
            self.report({'ERROR'}, "Please save your .blend file first.")
            return {'CANCELLED'}

        blend_dir = os.path.dirname(bpy.data.filepath)
        folder = os.path.join(blend_dir, "rig")
        filename = obj.name.lower().replace(" ", "_") + "_rig.txt"
        out_path = os.path.join(folder, filename)

        try:
            written = export_rig_to_starfall_text(context, obj, out_path)
        except Exception as e:
            import traceback
            traceback.print_exc()
            self.report({'ERROR'}, f"Export failed: {e}")
            return {'CANCELLED'}

        self.report({'INFO'}, f"Exported rig to: {written}")
        return {'FINISHED'}


class STARFALL_OT_export_anim(bpy.types.Operator):
    bl_idname = "export.starfall_anim"
    bl_label = "Export Anim (.txt)"
    bl_description = "Export keyframes of the active Action"
    bl_options = {'REGISTER'}

    def execute(self, context):
        obj = context.active_object
        if not obj or obj.type != 'ARMATURE':
            self.report({'ERROR'}, "Select an Armature object.")
            return {'CANCELLED'}

        arm = obj
        action = arm.animation_data.action if arm.animation_data else None
        if not action:
            self.report({'ERROR'}, "No Action found on the active Armature.")
            return {'CANCELLED'}

        if not bpy.data.is_saved:
            self.report({'ERROR'}, "Please save your .blend file first.")
            return {'CANCELLED'}

        blend_dir = os.path.dirname(bpy.data.filepath)
        folder = os.path.join(blend_dir, "anim")
        filename = action.name.lower().replace(" ", "_") + ".txt"
        out_path = os.path.join(folder, filename)

        try:
            written = export_action_to_starfall_text(context, arm, action, out_path)
        except Exception as e:
            import traceback
            traceback.print_exc()
            self.report({'ERROR'}, f"Export failed: {e}")
            return {'CANCELLED'}

        self.report({'INFO'}, f"Exported '{action.name}' to: {written}")
        return {'FINISHED'}

class STARFALL_PT_panel(bpy.types.Panel):
    bl_label = "Export to Starfall"
    bl_idname = "STARFALL_PT_panel"
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = "data"
    bl_options = {'DEFAULT_CLOSED'}

    @classmethod
    def poll(cls, context):
        ob = context.object
        return ob is not None and ob.type == 'ARMATURE'

    def draw(self, context):
        layout = self.layout
        layout.label(text="Export current Action:")
        layout.operator("export.starfall_rig", icon='ARMATURE_DATA')
        layout.operator("export.starfall_anim", icon='EXPORT')

def menu_func(self, context):
    self.layout.operator(STARFALL_OT_export_rig.bl_idname, icon='EXPORT')
    self.layout.operator(STARFALL_OT_export_anim.bl_idname, icon='EXPORT')
    

classes = (
    STARFALL_OT_export_rig,
    STARFALL_OT_export_anim,
    STARFALL_PT_panel,
)

def register():
    for c in classes:
        bpy.utils.register_class(c)
    bpy.types.VIEW3D_MT_object.append(menu_func)

def unregister():
    bpy.types.VIEW3D_MT_object.remove(menu_func)
    for c in reversed(classes):
        bpy.utils.unregister_class(c)

if __name__ == "__main__":
    register()
