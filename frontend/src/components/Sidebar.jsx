import { Badge, Button, IconAction, Select } from './primitives';
import { Plus, Settings, Trash2 } from 'lucide-react';

export default function Sidebar({
  conversations,
  currentConversationId,
  onSelectConversation,
  onNewConversation,
  onDeleteConversation,
  profiles,
  selectedProfileId,
  onSelectProfile,
  packets,
  selectedPacketId,
  onSelectPacket,
  selectedModelPairingLabel,
  onOpenSettings,
}) {
  const profileOptions = profiles.map((profile) => ({
    value: profile.id,
    label: profile.name,
  }));
  const packetOptions =
    packets.length === 0
      ? [{ value: '', label: 'No packets found' }]
      : packets.map((packet) => ({
          value: packet.packet_id,
          label: packet.title,
        }));

  return (
    <aside className="flex h-full w-[320px] flex-col border-r border-border bg-card">
      <div className="space-y-4 border-b border-border p-4">
        <div className="flex items-center justify-between">
          <h1 className="text-lg font-semibold text-foreground">LLM Council</h1>
        </div>
        <Button className="w-full justify-start gap-2" onClick={onNewConversation}>
          <Plus className="size-4" aria-hidden="true" />
          New Conversation
        </Button>

        <div className="space-y-2">
          <label className="text-xs font-semibold uppercase tracking-wide text-muted-foreground" htmlFor="profile-select">
            Council Profile
          </label>
          <Select
            id="profile-select"
            value={selectedProfileId || ''}
            onChange={(e) => onSelectProfile(e.target.value)}
            options={profileOptions}
            placeholder="Select profile"
          />

          <label className="text-xs font-semibold uppercase tracking-wide text-muted-foreground" htmlFor="packet-select">
            Research Packet
          </label>
          <Select
            id="packet-select"
            value={selectedPacketId || ''}
            onChange={(e) => onSelectPacket(e.target.value)}
            options={packetOptions}
            placeholder="Select packet"
          />
        </div>
      </div>

      <div className="flex-1 space-y-2 overflow-y-auto p-3">
        {conversations.length === 0 ? (
          <div className="rounded-md border border-dashed border-border bg-muted/20 p-3 text-sm text-muted-foreground">
            No conversations yet
          </div>
        ) : (
          conversations.map((conv) => (
            <div
              key={conv.id}
              className={`flex items-center justify-between gap-2 rounded-md border p-2 transition-colors ${
                conv.id === currentConversationId
                  ? 'border-primary bg-primary/10'
                  : 'border-border bg-background hover:bg-muted/40'
              }`}
              onClick={() => onSelectConversation(conv.id)}
            >
              <div className="min-w-0 flex-1">
                <div className="truncate text-sm font-medium text-foreground">
                  {conv.title || 'New Conversation'}
                </div>
                <div className="text-xs text-muted-foreground">
                  {conv.message_count} messages
                </div>
              </div>

              <IconAction
                icon={<Trash2 className="size-4" />}
                tooltip="Delete conversation"
                variant="destructive"
                onClick={(e) => {
                  e.stopPropagation();
                  onDeleteConversation(conv.id);
                }}
              />
            </div>
          ))
        )}
      </div>

      <div className="border-t border-border p-3">
        <Button type="button" variant="ghost" className="w-full justify-start gap-2" onClick={onOpenSettings}>
          <Settings className="size-4" aria-hidden="true" />
          Settings
        </Button>
        {selectedModelPairingLabel && (
          <div className="mt-2 flex items-center gap-2 px-4 text-sm text-muted-foreground">
            <span>Model Pairing:</span>
            <Badge className="max-w-[190px] truncate text-foreground">
              {selectedModelPairingLabel}
            </Badge>
          </div>
        )}
      </div>
    </aside>
  );
}
