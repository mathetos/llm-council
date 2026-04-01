import { Button, Modal, Select, TabBar, TextLink } from './primitives';

export default function SettingsModal({
  isOpen,
  onClose,
  pairings,
  selectedPairingId,
  onSelectPairing,
  profiles,
  activeProfileId,
  onSelectProfileTab,
  roleCardsByProfile,
  roleAssignmentsByProfile,
  duplicateRoleWarning,
  onChangeRoleAssignment,
  onApplySmartDefaults,
  modelOptionsState,
  onRefreshModels,
}) {
  if (!isOpen) {
    return null;
  }

  const selectedPairing =
    pairings.find((pairing) => pairing.id === selectedPairingId) || pairings[0];
  const roleCards = roleCardsByProfile?.[activeProfileId] || [];
  const roleAssignments = roleAssignmentsByProfile?.[activeProfileId] || {};
  const dropdownModels = (modelOptionsState?.models || []).map((item) => item.id);
  const profileTabOptions = profiles.map((profile) => ({
    value: profile.id,
    label: profile.name,
  }));
  const lastRefreshedLabel = modelOptionsState?.lastRefreshedAt
    ? new Date(modelOptionsState.lastRefreshedAt).toLocaleString()
    : 'Never';

  return (
    <Modal
      open={isOpen}
      onClose={onClose}
      title="Settings"
      description="Configure model pairing and profile role assignments."
      contentClassName="w-[min(980px,calc(100%-40px))] max-h-[90vh] overflow-y-auto"
      primaryAction="Close"
      secondaryAction=""
      onPrimaryAction={onClose}
      onSecondaryAction={onClose}
    >
      <div className="space-y-4">
        <div className="space-y-1">
          <h3 className="font-semibold text-foreground">Model Pairing</h3>
          <Select
            id="model-pairing-select"
            value={selectedPairingId}
            onChange={(e) => onSelectPairing(e.target.value)}
            options={pairings.map((pairing) => ({ value: pairing.id, label: pairing.label }))}
            placeholder="Select model pairing"
          />
          {selectedPairing?.description ? (
            <p className="text-xs text-muted-foreground">{selectedPairing.description}</p>
          ) : null}
        </div>

        <div className="space-y-2 rounded-md border border-border bg-muted/30 p-3 text-sm text-muted-foreground">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <p>
              Using cached privacy-safe models. Last refreshed: <span className="text-foreground">{lastRefreshedLabel}</span>
            </p>
            <Button
              type="button"
              size="sm"
              variant="secondary"
              onClick={onRefreshModels}
              isLoading={Boolean(modelOptionsState?.isLoading)}
            >
              Refresh models
            </Button>
          </div>
          {modelOptionsState?.isCheckingUpdates ? (
            <p>Checking for model catalog updates in the background...</p>
          ) : null}
          {modelOptionsState?.hasNewModels ? (
            <div className="rounded-md border border-primary/30 bg-primary/10 px-3 py-2 text-foreground">
              New models available. Click <span className="font-semibold">Refresh models</span> to update this list.
            </div>
          ) : null}
          {modelOptionsState?.error ? <p>{modelOptionsState.error}</p> : null}
          {modelOptionsState?.catalogError ? <p>{modelOptionsState.catalogError}</p> : null}
          {!dropdownModels.length && !modelOptionsState?.isLoading ? (
            <p>No cached privacy-safe models yet. Click Refresh models to load them.</p>
          ) : null}
        </div>

        <div className="overflow-hidden rounded-md border border-border bg-background">
          <div className="border-b border-border bg-muted/40 p-2">
            <TabBar
              value={activeProfileId}
              onChange={onSelectProfileTab}
              options={profileTabOptions}
              className="w-full overflow-x-auto border-0 bg-transparent p-0"
            />
          </div>
          <div className="space-y-4 p-4">
            <div className="flex items-center justify-between gap-3">
              <h3 className="font-semibold text-foreground">
                Role Assignments ({profiles.find((p) => p.id === activeProfileId)?.name || ''})
              </h3>
              <TextLink
                as="button"
                variant="muted"
                onClick={() => onApplySmartDefaults(activeProfileId)}
                disabled={modelOptionsState?.isLoading || !dropdownModels.length}
              >
                Reset
              </TextLink>
            </div>
            <p className="text-xs text-muted-foreground">
              Defaults are selected by role fit using model capability hints.
            </p>

            {roleCards.map((role) => (
              <div key={role.id} className="space-y-3 py-2">
                <div className="space-y-1">
                  <h4 className="font-semibold text-foreground">{role.name}</h4>
                  {role.must_include?.length ? (
                    <p className="text-xs text-muted-foreground">Focus: {role.must_include.join(' | ')}</p>
                  ) : null}
                </div>

                <div className="grid items-center gap-6 md:grid-cols-2">
                  <div className="text-sm leading-relaxed text-muted-foreground">
                    {role.mandate || 'No role mandate configured.'}
                  </div>
                  <Select
                    id={`role-${role.id}`}
                    value={roleAssignments[role.id] || ''}
                    onChange={(e) => onChangeRoleAssignment(activeProfileId, role.id, e.target.value)}
                    options={dropdownModels.map((model) => ({ value: model, label: model }))}
                    placeholder="No privacy-safe models available"
                    disabled={!dropdownModels.length}
                  />
                </div>
              </div>
            ))}

            {duplicateRoleWarning ? (
              <div className="rounded-md border border-primary/30 bg-primary/10 px-3 py-2 text-xs text-foreground">
                {duplicateRoleWarning}
              </div>
            ) : null}
          </div>
        </div>
      </div>
    </Modal>
  );
}
