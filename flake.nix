{
  description = "PieMenu FreeCAD addon - hermetic dev shell + fast launch/watch/smoke loop";

  # Pinned to a nixos-unstable rev where freecad 1.1.1 (and its vtk-9.5.2) are
  # CACHED on cache.nixos.org, so the whole environment substitutes with ZERO
  # source build and is fully hermetic. (The system's own pin, 241313f, cannot
  # build plain pkgs.freecad -- vtk-9.5.2 fails under gcc-15 there and Hydra never
  # cached it; the fix landed upstream, so this newer rev just fetches it.)
  # Bump with: nix flake update  (re-verify freecad stays cached before committing).
  inputs.nixpkgs.url = "github:NixOS/nixpkgs/643809054d65fdd466a63e3155b8c498cb483c04";

  outputs = { self, nixpkgs }:
    let
      system = "x86_64-linux";
      pkgs = nixpkgs.legacyPackages.${system};
      freecad = pkgs.freecad;   # hermetic 1.1.1, substituted from cache (no build)

      # Wrapper bodies are read from real repo files (builtins.readFile) so there is
      # no nix `${}` escaping and the scripts stay editable / runnable standalone;
      # writeShellApplication only adds a bash shebang + shellcheck. Each wrapper's
      # runtimeInputs pin its tools onto PATH, so `nix run` is hermetic regardless of
      # the ambient profile.
      mkWrapper = name: deps: pkgs.writeShellApplication {
        inherit name;
        runtimeInputs = [ pkgs.coreutils ] ++ deps;
        text = builtins.readFile (./dev + "/${name}.sh");
      };
      pm-launch = mkWrapper "pm-launch" [ freecad ];
      pm-smoke = mkWrapper "pm-smoke" [ freecad ];
      pm-e2e = mkWrapper "pm-e2e" [ freecad ];
      # pm-watch reuses pm-launch: entr -rd restarts it whenever a .py file changes.
      pm-watch = mkWrapper "pm-watch" [ pkgs.entr pkgs.findutils pm-launch ];
    in {
      devShells.${system}.default = pkgs.mkShell {
        packages = [
          freecad        # hermetic freecad + freecadcmd on PATH
          pkgs.python3   # 3.14.6 - py_compile syntax lint only; CANNOT import FreeCAD
          pkgs.ruff      # 0.15.22 - lint
          pm-launch
          pm-watch
          pm-smoke
          pm-e2e
        ];
        shellHook = ''
          echo "PieMenu dev shell (freecad: $(command -v freecad))"
          echo "  pm-watch    auto-relaunch FreeCAD on any .py change   <- the fast loop"
          echo "  pm-launch   isolated FreeCAD GUI, this repo as addon (throwaway config)"
          echo "  pm-smoke    headless smoke test -> SMOKE-PASS"
          echo "  pm-e2e      offscreen GUI end-to-end -> E2E-PASS"
          echo "  ruff check . ; python -m py_compile InitGui.py"
          echo "  scratch config: ''${PIEMENU_DEV:-/tmp/piemenu-dev}  (rm -rf to reset)"
        '';
      };

      apps.${system} = {
        launch  = { type = "app"; program = "${pm-launch}/bin/pm-launch"; };
        watch   = { type = "app"; program = "${pm-watch}/bin/pm-watch"; };
        smoke   = { type = "app"; program = "${pm-smoke}/bin/pm-smoke"; };
        e2e     = { type = "app"; program = "${pm-e2e}/bin/pm-e2e"; };
        default = self.apps.${system}.watch;
      };
    };
}
