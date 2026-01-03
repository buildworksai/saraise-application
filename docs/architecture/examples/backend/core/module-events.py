# ---------------------------------------------------------------------------------------------
#  Copyright (c) BuildWorks.AI. All rights reserved.
#  Licensed under the Apache 2.0 License. See License.txt in the project root for license information.
# ---------------------------------------------------------------------------------------------

# ✅ REQUIRED: Module event system
# backend/src/core/module_events.py
from typing import Dict, List, Callable, Any
import asyncio

class ModuleEventSystem:
    def __init__(self):
        self.event_handlers: Dict[str, List[Callable]] = {}

    def subscribe(self, event_name: str, handler: Callable):
        """Subscribe to module event"""
        if event_name not in self.event_handlers:
            self.event_handlers[event_name] = []
        self.event_handlers[event_name].append(handler)

    def emit(self, event_name: str, data: Dict[str, Any]):
        """Emit module event"""
        handlers = self.event_handlers.get(event_name, [])
        tasks = [handler(data) for handler in handlers]
        asyncio.gather(*tasks, return_exceptions=True)

# Global event system
module_events = ModuleEventSystem()

# Usage in module
# def create("/items")
# def create_item(item_data: ModuleItemCreate, ...):
#     """Create item and emit event"""
#     item = service.create_item(item_data, tenant_id)
#
#     # Emit event for other modules
#     module_events.emit("module_name.item.created", {
#         "item_id": item.module_id,
#         "tenant_id": tenant_id
#     })
#
#     return item
#
# # Subscribe in another module
# module_events.subscribe("module_name.item.created", handle_item_created)

