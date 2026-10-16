import type { ComponentProps } from 'react';
import { Icon } from './components';

export function SvgIcon({ svg, ...props }: { svg: string } & ComponentProps<typeof Icon>) {
  return <Icon {...props} dangerouslySetInnerHTML={{ __html: svg }} />;
}
