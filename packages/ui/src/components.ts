import * as React from 'react';
import { createComponent, type EventName } from '@lit/react';
import { MdElevatedButton } from '@material/web/button/elevated-button.js';
import { MdFilledButton } from '@material/web/button/filled-button.js';
import { MdFilledTonalButton } from '@material/web/button/filled-tonal-button.js';
import { MdOutlinedButton } from '@material/web/button/outlined-button.js';
import { MdTextButton } from '@material/web/button/text-button.js';
import { MdCheckbox } from '@material/web/checkbox/checkbox.js';
import { MdAssistChip } from '@material/web/chips/assist-chip.js';
import { MdChipSet } from '@material/web/chips/chip-set.js';
import { MdFilterChip } from '@material/web/chips/filter-chip.js';
import { MdInputChip } from '@material/web/chips/input-chip.js';
import { MdSuggestionChip } from '@material/web/chips/suggestion-chip.js';
import { MdDialog } from '@material/web/dialog/dialog.js';
import { MdDivider } from '@material/web/divider/divider.js';
import { MdElevation } from '@material/web/elevation/elevation.js';
import { MdBrandedFab } from '@material/web/fab/branded-fab.js';
import { MdFab } from '@material/web/fab/fab.js';
import { MdIcon } from '@material/web/icon/icon.js';
import { MdFilledIconButton } from '@material/web/iconbutton/filled-icon-button.js';
import { MdFilledTonalIconButton } from '@material/web/iconbutton/filled-tonal-icon-button.js';
import { MdIconButton } from '@material/web/iconbutton/icon-button.js';
import { MdOutlinedIconButton } from '@material/web/iconbutton/outlined-icon-button.js';
import { MdBadge } from '@material/web/labs/badge/badge.js';
import { MdElevatedCard } from '@material/web/labs/card/elevated-card.js';
import { MdFilledCard } from '@material/web/labs/card/filled-card.js';
import { MdOutlinedCard } from '@material/web/labs/card/outlined-card.js';
import { MdNavigationBar } from '@material/web/labs/navigationbar/navigation-bar.js';
import { MdNavigationDrawer } from '@material/web/labs/navigationdrawer/navigation-drawer.js';
import { MdNavigationDrawerModal } from '@material/web/labs/navigationdrawer/navigation-drawer-modal.js';
import { MdNavigationTab } from '@material/web/labs/navigationtab/navigation-tab.js';
import { MdOutlinedSegmentedButton } from '@material/web/labs/segmentedbutton/outlined-segmented-button.js';
import { MdOutlinedSegmentedButtonSet } from '@material/web/labs/segmentedbuttonset/outlined-segmented-button-set.js';
import { MdList } from '@material/web/list/list.js';
import { MdListItem } from '@material/web/list/list-item.js';
import { MdMenu } from '@material/web/menu/menu.js';
import { MdMenuItem } from '@material/web/menu/menu-item.js';
import { MdSubMenu } from '@material/web/menu/sub-menu.js';
import { MdCircularProgress } from '@material/web/progress/circular-progress.js';
import { MdLinearProgress } from '@material/web/progress/linear-progress.js';
import { MdRadio } from '@material/web/radio/radio.js';
import { MdRipple } from '@material/web/ripple/ripple.js';
import { MdFilledSelect } from '@material/web/select/filled-select.js';
import { MdOutlinedSelect } from '@material/web/select/outlined-select.js';
import { MdSelectOption } from '@material/web/select/select-option.js';
import { MdSlider } from '@material/web/slider/slider.js';
import { MdSwitch } from '@material/web/switch/switch.js';
import { MdPrimaryTab } from '@material/web/tabs/primary-tab.js';
import { MdSecondaryTab } from '@material/web/tabs/secondary-tab.js';
import { MdTabs } from '@material/web/tabs/tabs.js';
import { MdFilledTextField } from '@material/web/textfield/filled-text-field.js';
import { MdOutlinedTextField } from '@material/web/textfield/outlined-text-field.js';

// ponytail: this barrel registers every Material Web element (~500 kB min JS). Split into per-component
// subpath exports if the patient PWA's first load gets too slow.
const wrap = <I extends HTMLElement, E extends Record<string, EventName | string> = {}>(
  tagName: string,
  elementClass: new () => I,
  events?: E,
) => createComponent({ react: React, tagName, elementClass, events });

const formEvents = { onInput: 'input', onChange: 'change' } as const;
const overlayEvents = { onOpening: 'opening', onOpened: 'opened', onClosing: 'closing', onClosed: 'closed' } as const;

export const ElevatedButton = wrap('md-elevated-button', MdElevatedButton);
export const FilledButton = wrap('md-filled-button', MdFilledButton);
export const FilledTonalButton = wrap('md-filled-tonal-button', MdFilledTonalButton);
export const OutlinedButton = wrap('md-outlined-button', MdOutlinedButton);
export const TextButton = wrap('md-text-button', MdTextButton);

export const IconButton = wrap('md-icon-button', MdIconButton, formEvents);
export const FilledIconButton = wrap('md-filled-icon-button', MdFilledIconButton, formEvents);
export const FilledTonalIconButton = wrap('md-filled-tonal-icon-button', MdFilledTonalIconButton, formEvents);
export const OutlinedIconButton = wrap('md-outlined-icon-button', MdOutlinedIconButton, formEvents);

export const Fab = wrap('md-fab', MdFab);
export const BrandedFab = wrap('md-branded-fab', MdBrandedFab);

export const Checkbox = wrap('md-checkbox', MdCheckbox, formEvents);
export const Radio = wrap('md-radio', MdRadio, formEvents);
export const Switch = wrap('md-switch', MdSwitch, formEvents);
export const Slider = wrap('md-slider', MdSlider, formEvents);
export const FilledTextField = wrap('md-filled-text-field', MdFilledTextField, formEvents);
export const OutlinedTextField = wrap('md-outlined-text-field', MdOutlinedTextField, formEvents);
export const FilledSelect = wrap('md-filled-select', MdFilledSelect, formEvents);
export const OutlinedSelect = wrap('md-outlined-select', MdOutlinedSelect, formEvents);
export const SelectOption = wrap('md-select-option', MdSelectOption);

export const ChipSet = wrap('md-chip-set', MdChipSet);
export const AssistChip = wrap('md-assist-chip', MdAssistChip);
export const FilterChip = wrap('md-filter-chip', MdFilterChip, { ...formEvents, onRemove: 'remove' });
export const InputChip = wrap('md-input-chip', MdInputChip, { onRemove: 'remove' });
export const SuggestionChip = wrap('md-suggestion-chip', MdSuggestionChip);

export const Dialog = wrap('md-dialog', MdDialog, {
  onOpen: 'open',
  onOpened: 'opened',
  onClose: 'close',
  onClosed: 'closed',
  onCancel: 'cancel',
});
export const Menu = wrap('md-menu', MdMenu, overlayEvents);
export const MenuItem = wrap('md-menu-item', MdMenuItem);
export const SubMenu = wrap('md-sub-menu', MdSubMenu);

export const List = wrap('md-list', MdList);
export const ListItem = wrap('md-list-item', MdListItem);
export const Divider = wrap('md-divider', MdDivider);
export const Elevation = wrap('md-elevation', MdElevation);
export const Ripple = wrap('md-ripple', MdRipple);
export const Icon = wrap('md-icon', MdIcon);
export const Badge = wrap('md-badge', MdBadge);

export const CircularProgress = wrap('md-circular-progress', MdCircularProgress);
export const LinearProgress = wrap('md-linear-progress', MdLinearProgress);

export const Tabs = wrap('md-tabs', MdTabs, { onChange: 'change' });
export const PrimaryTab = wrap('md-primary-tab', MdPrimaryTab);
export const SecondaryTab = wrap('md-secondary-tab', MdSecondaryTab);

export const ElevatedCard = wrap('md-elevated-card', MdElevatedCard);
export const FilledCard = wrap('md-filled-card', MdFilledCard);
export const OutlinedCard = wrap('md-outlined-card', MdOutlinedCard);

export const NavigationBar = wrap('md-navigation-bar', MdNavigationBar, {
  onActivated: 'navigation-bar-activated' as EventName<CustomEvent<{ tab: HTMLElement; activeIndex: number }>>,
});
export const NavigationTab = wrap('md-navigation-tab', MdNavigationTab);
export const NavigationDrawer = wrap('md-navigation-drawer', MdNavigationDrawer, {
  onChanged: 'navigation-drawer-changed',
});
export const NavigationDrawerModal = wrap('md-navigation-drawer-modal', MdNavigationDrawerModal, {
  onChanged: 'navigation-drawer-changed',
});

export const OutlinedSegmentedButton = wrap('md-outlined-segmented-button', MdOutlinedSegmentedButton);
export const OutlinedSegmentedButtonSet = wrap('md-outlined-segmented-button-set', MdOutlinedSegmentedButtonSet, {
  onSelection: 'segmented-button-set-selection',
});
