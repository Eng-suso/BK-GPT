import type { Preview } from "@storybook/react";

import "@fontsource-variable/geist";
import "@fontsource-variable/geist-mono";

import "../styles/tokens/primitive.css";
import "../styles/tokens/semantic.css";
import "../src/styles/theme.css";

const preview: Preview = {
  parameters: {
    controls: {
      matchers: {
        color: /(background|color)$/i,
        date: /Date$/i,
      },
    },
  },
};

export default preview;
