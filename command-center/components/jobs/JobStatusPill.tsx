import { StatusPill } from "@/components/ui";

export type JobStatus = "QUEUED" | "RUNNING" | "COMPLETED" | "FAILED";

const MAP: Record<JobStatus, "run" | "ok" | "fail" | "idle"> = {
  QUEUED: "idle",
  RUNNING: "run",
  COMPLETED: "ok",
  FAILED: "fail",
};

/** A status pill for a derived job, mapping the job status to a UI tone. */
export function JobStatusPill({ status }: { status: JobStatus }) {
  return <StatusPill tone={MAP[status]} label={status} />;
}
