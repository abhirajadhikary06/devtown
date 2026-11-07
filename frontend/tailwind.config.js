/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: { paper: "#EDF0F7", ink: "#1E2440", plum: "#5B3B8C", marigold: "#F2B134", canal: "#2A8F9E", mist: "#D9DEEC" },
      fontFamily: { display: ['"Bricolage Grotesque"', "system-ui", "sans-serif"], body: ['"Instrument Sans"', "system-ui", "sans-serif"] },
    },
  },
  plugins: [],
};
