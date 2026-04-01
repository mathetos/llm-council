import { useState } from 'react'
import { createRoot } from 'react-dom/client'
import {
  Accordion,
  Alert,
  Button,
  Calendar,
  DateRangePicker,
  DefaultsSummary,
  FieldGroup,
  IconAction,
  Input,
  Modal,
  PresetOrCustomPicker,
  Select,
  TabBar,
  TextLink,
  Toggle,
  ToggleRevealRow,
  Tooltip,
} from './components/primitives'
import './index.css'
import { Copy, Trash2 } from 'lucide-react'

export function PreviewCard({ title, children }) {
  return (
    <section className="rounded-xl border border-border bg-card p-5 shadow-sm">
      <h2 className="mb-4 text-lg font-semibold text-foreground">{title}</h2>
      {children}
    </section>
  )
}

export function DesignSystemPreview() {
  const [toggleValue, setToggleValue] = useState(false)
  const [tab, setTab] = useState('overview')
  const [showModal, setShowModal] = useState(false)
  const [date, setDate] = useState(null)
  const [range, setRange] = useState({ start: null, end: null })
  const [showTooltip, setShowTooltip] = useState(false)

  return (
    <main className="min-h-screen bg-background p-8 text-foreground">
      <div className="mx-auto max-w-6xl space-y-6">
        <header>
          <h1 className="text-2xl font-semibold">Design System Preview</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            RightTime-style primitives using semantic tokens and Tailwind utilities.
          </p>
        </header>

        <div className="grid gap-5 md:grid-cols-2">
          <PreviewCard title="Button + TextLink">
            <div className="flex flex-wrap gap-2">
              <Button variant="primary">Primary</Button>
              <Button variant="secondary">Secondary</Button>
              <Button variant="accent">Accent</Button>
              <Button variant="ghost">Ghost</Button>
            </div>
            <div className="mt-3 flex gap-3">
              <TextLink href="#" variant="primary">
                Primary link
              </TextLink>
              <TextLink as="button" variant="destructive">
                Destructive action
              </TextLink>
            </div>
          </PreviewCard>

          <PreviewCard title="Input / FieldGroup / Select">
            <div className="space-y-3">
              <Input id="preview-input" placeholder="Enter a value" />
              <FieldGroup
                label="Meeting time"
                helperText="Use business hours where possible"
                inputProps={{ id: 'preview-field-group', placeholder: '09:30 AM' }}
              />
              <Select
                value=""
                options={[
                  { value: '30', label: '30 minutes' },
                  { value: '60', label: '1 hour' },
                ]}
                placeholder="Select duration"
              />
            </div>
          </PreviewCard>

          <PreviewCard title="Toggle / ToggleRevealRow / Presets">
            <div className="space-y-3">
              <Toggle
                id="preview-toggle"
                label="Enable reminders"
                checked={toggleValue}
                onCheckedChange={setToggleValue}
              />
              <ToggleRevealRow
                label="Custom notice period"
                summary="Defaults apply (24 hours)"
                checked={toggleValue}
                onCheckedChange={setToggleValue}
              >
                <Input id="custom-notice-preview" placeholder="Minutes" />
              </ToggleRevealRow>
              <PresetOrCustomPicker
                label="Notice period"
                presets={[
                  { value: 'none', label: 'None' },
                  { value: '1h', label: '1 hour' },
                  { value: '24h', label: '24 hours' },
                ]}
                value="24h"
                onChange={() => {}}
              />
            </div>
          </PreviewCard>

          <PreviewCard title="Tabs / Accordion / DefaultsSummary">
            <div className="space-y-3">
              <TabBar
                value={tab}
                onChange={setTab}
                options={[
                  { value: 'overview', label: 'Overview' },
                  { value: 'details', label: 'Details' },
                  { value: 'history', label: 'History' },
                ]}
              />
              <Accordion title="Configuration details" description="Expanded content example" defaultOpen>
                <p className="text-sm text-muted-foreground">This accordion wraps progressive content.</p>
              </Accordion>
              <DefaultsSummary items={['Mon-Fri', '09:00-17:00', '2h notice']} />
            </div>
          </PreviewCard>

          <PreviewCard title="Modal + Alert">
            <div className="space-y-3">
              <Button variant="primary" onClick={() => setShowModal(true)}>
                Open modal
              </Button>
              <Alert variant="info" title="Note">
                Free models are filtered by privacy compatibility.
              </Alert>
            </div>
          </PreviewCard>

          <PreviewCard title="Calendar + DateRange + IconAction + Tooltip">
            <div className="space-y-3">
              <Calendar selectedDate={date} onDateSelect={setDate} disablePast />
              <DateRangePicker label="Availability" value={range} onChange={setRange} />
              <div className="flex items-center gap-2">
                <IconAction icon={<Copy className="size-4" />} tooltip="Copy" onClick={() => {}} />
                <IconAction
                  icon={<Trash2 className="size-4" />}
                  tooltip="Delete"
                  variant="destructive"
                  onClick={() => {}}
                />
                <span
                  className="relative rounded border border-border px-3 py-1 text-sm"
                  onMouseEnter={() => setShowTooltip(true)}
                  onMouseLeave={() => setShowTooltip(false)}
                >
                  Hover me
                  <Tooltip show={showTooltip} text="Tooltip" />
                </span>
              </div>
            </div>
          </PreviewCard>
        </div>
      </div>

      <Modal
        open={showModal}
        onClose={() => setShowModal(false)}
        title="Preview modal"
        description="Tokenized modal shell and button actions."
        primaryAction="Confirm"
        secondaryAction="Cancel"
        onPrimaryAction={() => setShowModal(false)}
        onSecondaryAction={() => setShowModal(false)}
      >
        <p className="text-sm text-muted-foreground">This validates modal primitives and focus behavior.</p>
      </Modal>
    </main>
  )
}

createRoot(document.getElementById('root')).render(<DesignSystemPreview />)
