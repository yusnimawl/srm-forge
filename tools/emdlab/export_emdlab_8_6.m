function export_emdlab_8_6(outDir)
% Export EMDLAB's 8/6 benchmark data for srm-forge validation fixtures:
%   emdlab_8_6_sweep.csv   EMDLAB static torque sweep (Arkkio, MST, co-energy derivative), psi, W, W'
%   m530_50a_bh.csv        the M530-50A B-H table EMDLAB uses (as shipped, no stacking factor)
%   maxwell_8_6_torque.csv ANSYS Maxwell static torque shipped with EMDLAB (srm-te-maxwell.tab)
% Needs EMDLAB at C:\emdlab-win64. Run: matlab -batch "export_emdlab_8_6('<dir>')"
addpath(genpath('C:\emdlab-win64'));
if nargin < 1, outDir = pwd; end
if ~exist(outDir, 'dir'), mkdir(outDir); end

N = 30;
thetaDeg = linspace(0, 30, N);
psi = zeros(N,1); W = zeros(N,1); Wc = zeros(N,1); Tark = zeros(N,1); Tmst = zeros(N,1); nodes = zeros(N,1);
for k = 1:N
    [psi(k), W(k), Wc(k), Tark(k), Tmst(k), nodes(k)] = solveAt(thetaDeg(k));
end
Tco = diff_cen(Wc', (pi/6)/(N-1))';
T = table(thetaDeg', thetaDeg' - 30, psi, W, Wc, Tark, Tmst, Tco, nodes, ...
    'VariableNames', {'theta_tab_deg','rotor_deg_from_aligned','psi_wb_turns','energy_j','coenergy_j', ...
                      'torque_arkkio_nm','torque_mst_nm','torque_coenergy_nm','nodes'});
writetable(T, fullfile(outDir, 'emdlab_8_6_sweep.csv'));

mat = emdlab_mlib_es_M530_50A;
writetable(array2table(mat.hb_curve, 'VariableNames', {'h_a_per_m','b_t'}), fullfile(outDir, 'm530_50a_bh.csv'));

fid = fopen('C:\emdlab-win64\examples\switched-reluctance-machine\srm-te-maxwell.tab', 'r');
fgetl(fid); d = fscanf(fid, '%f'); fclose(fid);
d = reshape(d, 2, [])';
writetable(array2table([d(:,1), d(:,1) - 30, d(:,2)], 'VariableNames', ...
    {'theta_tab_deg','rotor_deg_from_aligned','torque_nm'}), fullfile(outDir, 'maxwell_8_6_torque.csv'));
fprintf('wrote 3 files to %s\n', outDir);
end

function [psi, W, Wc, Tark, Tmst, nn] = solveAt(thetaDeg)
% Geometry, mesh and excitation of examples/switched-reluctance-machine/emdlab_examples_srm86_static_torque.m
Ns = 8; Nr = 6; Dsh = 20; ISD = 74; OSD = 125; gap = 0.5;
beta_r = 19.8*pi/180; beta_s = 17.1*pi/180; wry = 7.53; wsy = 7.7;
f_mesh = @(r) interp1([Dsh/2,ISD/2,OSD/2], [wry/2,gap,wsy/2], r);
g = emdlab_g2d_db;
emdlab_g2d_lib_srm1(g, Ns, Nr, Dsh, ISD, OSD, gap, beta_r, beta_s, wry, wsy);
g.setMeshLengthByRadialFunction(f_mesh);
evalc('m = g.generateMesh(''mg0'');'); m.setPrintFlag(0);
m.addMaterial('m530', emdlab_mlib_es_M530_50A); m.addMaterial('copper', emdlab_mlib_copper);
m.setMaterial('Rotor','m530'); m.setMaterial('Stator','m530'); m.setMaterial('sca','copper');
m.aux_cmxjcrj('Rotor', Nr); m.aux_cmxjcrj('Stator', Ns); m.aux_cmxjcrj('RotorAP', Nr); m.aux_cmxcr('sca', Ns);
m.rotateMeshZone('Rotor', (thetaDeg-30)*pi/180); m.rotateMeshZone('RotorAP', (thetaDeg-30)*pi/180);
m.aux_addCircularAirGap('ag',0,0,ISD/2-gap,0,0,ISD/2,2);
s = emdlab_solvers_ms2d_tl3_ihnl(m); s.setLengthUnit('mm'); s.setDepth(70);
s.defineCoil('phaseA');
s.addMeshZone2Coil('phaseA','sca11',278,1); s.addMeshZone2Coil('phaseA','sca21',278,-1);
s.addMeshZone2Coil('phaseA','sca15',278,-1); s.addMeshZone2Coil('phaseA','sca25',278,1);
s.setCoilCurrent('phaseA', 3.6); s.setAzBC(m.getfbn, 0);
evalc('s.solve;');
psi = s.evalCoilFluxLinkage('phaseA');
[W, Wc] = s.evalTotalEnergyCoenergy;
Tark = s.evalTorqueByArkkio('ag', gap);
Tmst = s.evalTorqueByMST3(0, 0, ISD/2-gap/2, gap);
nn = m.Nn;
end
