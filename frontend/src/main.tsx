import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import "./index.css";
import BannerPage from "./pages/BannerPage";
import CityPage from "./pages/CityPage";
import Landing from "./pages/Landing";
import Studio from "./pages/Studio";
import WorldPage from "./pages/WorldPage";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Landing />} />
        <Route path="/studio" element={<Studio />} />
        <Route path="/banner" element={<BannerPage />} />
        <Route path="/world" element={<WorldPage />} />
        <Route path="/u/:username" element={<CityPage />} />
        <Route path="/:handle" element={<CityPage />} />
      </Routes>
    </BrowserRouter>
  </React.StrictMode>
);
