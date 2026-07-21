import { useParams } from "react-router-dom";
import { ScheduleEditor } from "../components/ScheduleEditor";

export function ScheduleEditPage() {
  const { id = "" } = useParams();
  return <ScheduleEditor scheduleId={id} />;
}
