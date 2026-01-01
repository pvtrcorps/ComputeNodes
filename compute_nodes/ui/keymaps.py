import bpy

addon_keymaps = []

def register():
    wm = bpy.context.window_manager
    kc = wm.keyconfigs.addon
    if kc:
        km = kc.keymaps.new(name='Node Editor', space_type='NODE_EDITOR')
        
        # Ctrl+G -> Make Group
        kmi = km.keymap_items.new("compute.group_make", 'G', 'PRESS', ctrl=True)
        addon_keymaps.append((km, kmi))
        
        # Alt+G -> Ungroup
        kmi = km.keymap_items.new("compute.group_ungroup", 'G', 'PRESS', alt=True)
        addon_keymaps.append((km, kmi))
        
        # Double Click -> Enter/Exit Group
        kmi = km.keymap_items.new("compute.group_action", 'LEFTMOUSE', 'DOUBLE_CLICK')
        addon_keymaps.append((km, kmi))

def unregister():
    for km, kmi in addon_keymaps:
        km.keymap_items.remove(kmi)
    addon_keymaps.clear()
