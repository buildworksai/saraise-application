import { lazy } from "react";
import { MessageSquare, Settings, TableProperties, Workflow } from "lucide-react";
import type { TenantRoute } from "@/navigation/tenant-route-types";
import { ROUTES } from "./contracts";

const modes = ["development", "self-hosted", "saas"] as const;

export const tenantRoutes = [
  {
    id: "communication-hub.channels",
    module: "communication_hub",
    path: ROUTES.CHANNELS,
    title: "Communication channels",
    requiredPermission: "communication.channel:read",
    sourceFile: "modules/communication_hub/pages/ChannelListPage.tsx",
    Page: lazy(() =>
      import("./pages/ChannelListPage").then(({ ChannelListPage }) => ({
        default: ChannelListPage,
      }))
    ),
    modes,
    navigation: { type: "sidebar", label: "Channels", icon: MessageSquare, order: 1410 },
  },
  {
    id: "communication-hub.messages",
    module: "communication_hub",
    path: ROUTES.MESSAGES,
    title: "Communication messages",
    requiredPermission: "communication.message:read",
    sourceFile: "modules/communication_hub/pages/MessageListPage.tsx",
    Page: lazy(() =>
      import("./pages/MessageListPage").then(({ MessageListPage }) => ({
        default: MessageListPage,
      }))
    ),
    modes,
    navigation: { type: "sidebar", label: "Messages", icon: TableProperties, order: 1420 },
  },
  {
    id: "communication-hub.templates",
    module: "communication_hub",
    path: ROUTES.TEMPLATES,
    title: "Communication templates",
    requiredPermission: "communication.message:read",
    sourceFile: "modules/communication_hub/pages/TemplatesPage.tsx",
    Page: lazy(() =>
      import("./pages/TemplatesPage").then(({ TemplatesPage }) => ({ default: TemplatesPage }))
    ),
    modes,
    navigation: { type: "sidebar", label: "Templates", icon: Workflow, order: 1430 },
  },
  {
    id: "communication-hub.configuration",
    module: "communication_hub",
    path: ROUTES.CONFIGURATION,
    title: "Communication configuration",
    requiredPermission: "communication.channel:read",
    sourceFile: "modules/communication_hub/pages/ConfigurationPage.tsx",
    Page: lazy(() =>
      import("./pages/ConfigurationPage").then(({ ConfigurationPage }) => ({
        default: ConfigurationPage,
      }))
    ),
    modes,
    navigation: { type: "sidebar", label: "Configuration", icon: Settings, order: 1440 },
  },
] satisfies readonly TenantRoute[];

export default tenantRoutes;
