import type { Metadata } from "next";

import { ChatScreen } from "@/components/chat/ChatScreen";
import { institution } from "@/lib/institution";

export const metadata: Metadata = { title: `Chat · ${institution.productName}` };

/** Chat (DESIGN.md 3.2): WhatsApp-style chat over the /ws/chat WebSocket (M3). */
export default function ChatPage() {
  return <ChatScreen />;
}
