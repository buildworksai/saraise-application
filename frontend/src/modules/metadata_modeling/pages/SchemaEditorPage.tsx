import React, { useState, useEffect } from "react";
import { metadataService } from "../services/metadata-service";
import { EntityDefinition, FieldDefinition } from "../contracts";
import { FormBuilder } from "../components/FormBuilder";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { toast } from "sonner";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/Card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { DynamicForm } from "../components/DynamicForm";

export const SchemaEditorPage = () => {
  const [entities, setEntities] = useState<EntityDefinition[]>([]);
  const [selectedEntity, setSelectedEntity] = useState<EntityDefinition | null>(
    null
  );
  const [newEntityName, setNewEntityName] = useState("");
  const [testMode, setTestMode] = useState(false);

  useEffect(() => {
    loadEntities();
  }, []);

  const loadEntities = async () => {
    try {
      const data = await metadataService.getEntities();
      setEntities(data);
    } catch (e) {
      toast.error("Failed to load entities");
    }
  };

  const handleCreateEntity = async () => {
    if (!newEntityName) return;
    try {
      const newEntity = await metadataService.createEntity({
        name: newEntityName,
        code: newEntityName.toLowerCase().replace(/\\s+/g, "-"),
        is_system: false,
        fields: [],
      });
      setEntities([...entities, newEntity]);
      setSelectedEntity(newEntity);
      setNewEntityName("");
      toast.success("Entity created");
    } catch (e) {
      toast.error("Failed to create entity");
    }
  };

  const handleSaveFields = async (fields: FieldDefinition[]) => {
    // In backend, Entity update might need to handle nested fields or we create them separately.
    // For simplicity assuming API supports saving fields via Entity update or we iterate.
    // But our backend 'update' implementation in api.py (default ModelViewSet) doesn't automatically handle nested writes for `fields`.
    // We need to implement nested write or separate API calls.
    // For this Phase, let's assume we re-save the Entity but fields are read-only in serializer?
    // Wait, `fields` in `EntityDefinitionSerializer` was `read_only=True`.
    // I need to update the backend serializer to allow writing fields!

    toast.info(
      "Saving fields feature pending Backend Serializer update (Writable Nested Serializers)."
    );
  };

  // NOTE: To make this functional without complex nested serializer, we might need a separate endpoint for adding fields.
  // Or we update field definitions one by one.

  return (
    <div className="p-6 space-y-6">
      <h1 className="text-2xl font-bold">Metadata Modeling</h1>

      <div className="flex gap-6">
        {/* Sidebar */}
        <Card className="w-1/4 h-[calc(100vh-200px)]">
          <CardHeader>
            <CardTitle>Entities</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex gap-2">
              <Input
                placeholder="New Entity Name"
                value={newEntityName}
                onChange={(e) => setNewEntityName(e.target.value)}
              />
              <Button onClick={handleCreateEntity}>Add</Button>
            </div>
            <div className="space-y-2">
              {entities && entities.length > 0 ? (
                entities.map((e) => (
                  <div
                    key={e.id}
                    className={`p-2 cursor-pointer rounded ${
                      selectedEntity?.id === e.id
                        ? "bg-primary/10"
                        : "hover:bg-gray-100"
                    }`}
                    onClick={() => setSelectedEntity(e)}
                  >
                    {e.name}{" "}
                    <span className="text-xs text-gray-500">({e.code})</span>
                  </div>
                ))
              ) : (
                <div className="text-sm text-gray-500 p-2">
                  No entities yet. Create one above.
                </div>
              )}
            </div>
          </CardContent>
        </Card>

        {/* Editor */}
        <Card className="flex-1">
          {selectedEntity ? (
            <div className="p-6 space-y-6">
              <div className="flex justify-between items-center">
                <h2 className="text-xl font-semibold">
                  {selectedEntity.name} Schema
                </h2>
                <div className="flex gap-2">
                  <Button
                    variant="outline"
                    onClick={() => setTestMode(!testMode)}
                  >
                    {testMode ? "Edit Schema" : "Test Form"}
                  </Button>
                  <Button
                    onClick={() =>
                      handleSaveFields(selectedEntity.fields || [])
                    }
                  >
                    Save Changes
                  </Button>
                </div>
              </div>

              {testMode ? (
                <div className="max-w-xl mx-auto border p-6 rounded">
                  <h3 className="mb-4 text-lg font-medium">
                    Preview: New {selectedEntity.name}
                  </h3>
                  <DynamicForm
                    entityDef={selectedEntity}
                    onSubmit={(data) => {
                      console.log(data);
                      toast.success("Form submitted (Console Log)");
                    }}
                  />
                </div>
              ) : (
                <FormBuilder
                  fields={selectedEntity.fields || []}
                  onChange={(newFields) => {
                    // Update local state for preview
                    setSelectedEntity({ ...selectedEntity, fields: newFields });
                  }}
                />
              )}
            </div>
          ) : (
            <div className="flex items-center justify-center h-full text-gray-400">
              Select an entity to edit
            </div>
          )}
        </Card>
      </div>
    </div>
  );
};
