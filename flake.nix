{
  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";

    flake-parts.url = "github:hercules-ci/flake-parts";

    lumberjack-compiler = {
      url = "github:L-tips/lumberjack-compiler";
      inputs.nixpkgs.follows = "nixpkgs";
    };
  };

  outputs =
    inputs@{ flake-parts, ... }:
    flake-parts.lib.mkFlake { inherit inputs; } {

      systems = [
        "x86_64-linux"
        "aarch64-linux"
      ];

      perSystem =
        { pkgs, system, ... }:
        let
          veryl = pkgs.veryl.overrideAttrs (
            old:
            let
              src = pkgs.fetchFromGitHub {
                owner = "veryl-lang";
                repo = "veryl";
                rev = "81daeab2bf4596016db472fec72219a0098b18be";
                hash = "sha256-TB8gmURTH6SQJCl3n00okGvlN/viAqITAUVJonscbFQ=";
              };
            in
            {
              inherit src;

              cargoDeps = pkgs.rustPlatform.fetchCargoVendor {
                inherit src;
                name = "veryl";
                hash = "sha256-/BKVUz3m26MvUvxp9Irtfd0RhbGVZPC2wnZ+Ow1evtU=";
              };
            }
          );
        in
        {
          devShells.default = pkgs.mkShell {
            nativeBuildInputs = with pkgs; [
              veryl
              verilator
              uv
              surfer
              zlib

              inputs.lumberjack-compiler.packages.${system}.default
            ];
          };
        };
    };
}
