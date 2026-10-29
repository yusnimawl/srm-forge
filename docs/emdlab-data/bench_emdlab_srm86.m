function bench_emdlab_srm86()
% Staged timing of the emdlab 8/6 SRM static solve, at the example's mesh and at refined meshes.
addpath(genpath('C:\emdlab-win64'));
fprintf('MATLAB %s, maxNumCompThreads=%d\n', version, maxNumCompThreads);
for scale = [1, 0.5, 0.3, 0.2]
    run_one(scale, -15);
end
% one-thread run to show MATLAB's own threading contribution
maxNumCompThreads(1);
fprintf('--- single thread ---\n');
run_one(1, -15); run_one(0.3, -15);
end

function run_one(scale, rotorPosition)
gv_Ns = 8; gv_Nr = 6; gv_Dsh = 20; gv_ISD = 74; gv_OSD = 125; gv_gap = 0.5;
gv_beta_r = 19.8*pi/180; gv_beta_s = 17.1*pi/180; gv_wry = 7.53; gv_wsy = 7.7;
f_mesh = @(r) scale*interp1([gv_Dsh/2,gv_ISD/2,gv_OSD/2], [gv_wry/2,0.4,gv_wsy/2], r, 'linear','extrap');
t0 = tic;
g = emdlab_g2d_db;
emdlab_g2d_lib_srm1(g, gv_Ns, gv_Nr, gv_Dsh, gv_ISD, gv_OSD, gv_gap, gv_beta_r, gv_beta_s, gv_wry, gv_wsy);
g.setMeshLengthByRadialFunction(f_mesh);
evalc('m = g.generateMesh(''mg0'');');
m.setPrintFlag(0);
tGeomMesh = toc(t0);
t1 = tic;
m.addMaterial('m530', emdlab_mlib_es_M530_50A);
m.addMaterial('copper', emdlab_mlib_copper);
m.setMaterial('Rotor','m530'); m.setMaterial('Stator','m530'); m.setMaterial('sca','copper');
m.aux_cmxjcrj('Rotor', gv_Nr); m.aux_cmxjcrj('Stator', gv_Ns);
m.aux_cmxjcrj('RotorAP', gv_Nr); m.aux_cmxcr('sca', gv_Ns);
m.rotateMeshZone('Rotor', rotorPosition*pi/180);
m.rotateMeshZone('RotorAP', rotorPosition*pi/180);
m.aux_addCircularAirGap('ag',0,0,gv_ISD/2-gv_gap,0,0,gv_ISD/2,3);
tReplicate = toc(t1);
t2 = tic;
s = emdlab_solvers_ms2d_tl3_ihnl(m);
s.setLengthUnit('mm'); s.setDepth(70);
s.defineCoil('phaseA');
s.addMeshZone2Coil('phaseA','sca11',278,1); s.addMeshZone2Coil('phaseA','sca21',278,-1);
s.addMeshZone2Coil('phaseA','sca15',278,-1); s.addMeshZone2Coil('phaseA','sca25',278,1);
s.setCoilCurrent('phaseA', 3.6);
s.setAzBC(m.getfbn, 0);
tSetup = toc(t2);
t3 = tic;
evalc('s.solve;');
tSolve = toc(t3);
t4 = tic;
psi = s.evalCoilFluxLinkage('phaseA');
T = s.evalTorqueByArkkio('ag', gv_gap);
tPost = toc(t4);
h = s.solverHistory;
fprintf('scale=%.2f Nn=%6d Ne=%6d | geom+mesh %.2fs replicate+gap %.2fs setup %.2fs SOLVE %.2fs (%d it, %.3fs/it) post %.3fs | psi=%.5f T=%.4f relErr=%.1e\n', ...
    scale, m.Nn, m.Ne, tGeomMesh, tReplicate, tSetup, tSolve, h.iterations, tSolve/max(h.iterations,1), tPost, psi, T, h.relativeError(end));
end
