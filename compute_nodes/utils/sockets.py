# Socket management utilities for dynamic socket nodes
# Provides shared helpers for nodes like GroupInput/Output and Repeat zones

from functools import wraps


def with_sync_guard(method):
    """Decorator to prevent recursive sync calls.
    
    Use this on methods that clear and rebuild sockets, which can trigger
    tree updates via links.new() and cause infinite recursion.
    
    Example:
        @with_sync_guard
        def sync_from_interface(self):
            # ... socket rebuilding logic
    """
    @wraps(method)
    def wrapper(self, *args, **kwargs):
        if getattr(self, '_syncing', False):
            return
        self._syncing = True
        try:
            return method(self, *args, **kwargs)
        finally:
            self._syncing = False
    return wrapper


def save_output_links_by_identifier(sockets):
    """Save output socket links using stable identifiers.
    
    Args:
        sockets: Collection of output sockets
    
    Returns:
        Dict mapping socket.name -> [(to_node_name, to_socket_identifier), ...]
        
    Note: Uses socket.identifier instead of socket.name for stability.
    """
    saved = {}
    for sock in sockets:
        if sock.is_linked and sock.name != "Empty":
            saved[sock.name] = []
            for link in sock.links:
                saved[sock.name].append((
                    link.to_node.name,
                    link.to_socket.identifier
                ))
    return saved


def save_input_links_by_identifier(sockets):
    """Save input socket links using stable identifiers.
    
    Args:
        sockets: Collection of input sockets
    
    Returns:
        Dict mapping socket.name -> (from_node_name, from_socket_identifier)
        
    Note: Input sockets have max 1 link, so returns tuple instead of list.
    """
    saved = {}
    for sock in sockets:
        if sock.is_linked and sock.name != "Empty":
            link = sock.links[0]
            saved[sock.name] = (
                link.from_node.name,
                link.from_socket.identifier
            )
    return saved


def restore_output_links(tree, saved_links, sockets):
    """Restore output socket links from saved data.
    
    Args:
        tree: Node tree (for tree.nodes and tree.links)
        saved_links: Dict from save_output_links_by_identifier
        sockets: Collection of output sockets (to find by name)
    """
    for sock_name, link_list in saved_links.items():
        sock = sockets.get(sock_name)
        if not sock:
            continue
        
        for to_node_name, to_socket_id in link_list:
            to_node = tree.nodes.get(to_node_name)
            if to_node:
                to_sock = next(
                    (s for s in to_node.inputs if s.identifier == to_socket_id),
                    None
                )
                if to_sock:
                    tree.links.new(sock, to_sock)


def restore_input_links(tree, saved_links, sockets):
    """Restore input socket links from saved data.
    
    Args:
        tree: Node tree (for tree.nodes and tree.links)
        saved_links: Dict from save_input_links_by_identifier
        sockets: Collection of input sockets (to find by name)
    """
    for sock_name, (from_node_name, from_socket_id) in saved_links.items():
        sock = sockets.get(sock_name)
        if not sock:
            continue
        
        from_node = tree.nodes.get(from_node_name)
        if from_node:
            from_sock = next(
                (s for s in from_node.outputs if s.identifier == from_socket_id),
                None
            )
            if from_sock:
                tree.links.new(from_sock, sock)
