import { DesignLabContent } from "../../../.claude-design/lab/page";
import { FeedbackOverlay } from "./FeedbackOverlay";

export default function DesignLabPage() {
  return (
    <>
      <DesignLabContent />
      <FeedbackOverlay targetName="FullDashboardUI" />
    </>
  );
}
