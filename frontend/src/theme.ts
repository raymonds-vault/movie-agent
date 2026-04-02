import type { ThemeConfig } from 'antd'
import { theme } from 'antd'

const PRIMARY = '#EC407A'

/** Light theme only (Ant Design + app chrome). */
export function buildAntdTheme(): ThemeConfig {
  return {
    algorithm: theme.defaultAlgorithm,
    token: {
      colorPrimary: PRIMARY,
      colorBgBase: '#ffffff',
      colorTextBase: '#1a1a1a',
      borderRadius: 14,
      colorInfo: PRIMARY,
      fontFamily:
        "'Inter', system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif",
    },
    components: {
      Button: {
        primaryShadow: '0 4px 12px rgba(236, 64, 122, 0.35)',
      },
      Input: {
        activeBorderColor: PRIMARY,
        hoverBorderColor: '#F48FB1',
        colorBgContainer: '#ffffff',
      },
      Layout: {
        bodyBg: '#ffffff',
        headerBg: '#ffffff',
      },
    },
  }
}
