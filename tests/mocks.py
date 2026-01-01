from unittest.mock import MagicMock
print("DEBUG: LOADING MOCKS MODULE (RENAMED)")

class MockSocketNew:
    def __init__(self, name="Socket", default_value=0.0, type='VALUE'):
        self.name = name
        self.default_value = default_value
        self.type = type # VALUE, VECTOR, RGBA, INT, BOOLEAN, IMAGE
        self.is_linked = False
        self.links = []
        self.node = None # Parent node
        self.bl_idname = "NodeSocketFloat" # Default

    def as_pointer(self):
        return id(self)

class MockLinkNew:
    def __init__(self, from_socket, from_node, to_socket, to_node):
        self.from_socket = from_socket
        self.from_node = from_node
        self.to_socket = to_socket
        self.to_node = to_node

class MockSocketCollectionNew(list):
    """Simulates Blender's NodeInputs/NodeOutputs collection which supports indexing by name."""
    def __init__(self, owner_node=None):
        super().__init__()
        self.owner_node = owner_node

    def __getitem__(self, key):
        if isinstance(key, str):
            for sock in self:
                if sock.name == key:
                    return sock
            raise KeyError(key)
        return super().__getitem__(key)
    
    def __contains__(self, key):
        if isinstance(key, str):
            for sock in self:
                if sock.name == key:
                    return True
            return False
        return super().__contains__(key)
        
    def get(self, key, default=None):
        try:
            return self[key]
        except KeyError:
            return default
            
    def new(self, type, name):
        # Helper for some tests that might try to create sockets
        sock = MockSocketNew(name)
        sock.bl_idname = type
        self.append(sock)
        return sock
        
    def append(self, item):
        super().append(item)
        if self.owner_node:
            item.node = self.owner_node

class MockNodeNew:
    def __init__(self, bl_idname, name="Node", **kwargs):
        self.bl_idname = bl_idname
        self.name = name
        self.inputs = MockSocketCollectionNew(self)
        self.outputs = MockSocketCollectionNew(self)
        self.parent = None
        self.operation = 'ADD'
        self.image = None
        
        # Default properties for specific nodes
        self.format = 'RGBA32F'
        self.output_name = "Output"
        self.save_mode = 'DATABLOCK'
        self.dim_mode = '2D'
        
        # Apply specific kwargs
        for k, v in kwargs.items():
            setattr(self, k, v)


class MockNodeTreeNew:
    def __init__(self, name="Tree"):
        self.name = name
        self.nodes = MockSocketCollectionNew()
        self.interface = MagicMock() # For groups
        self.interface.items_tree = []
