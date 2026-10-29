% initialization

clear;
close all;
addpath(genpath('C:\emdlab-win64'));

Nposition = 30;
rotorPosition = linspace(0,30,Nposition);
Delta_Theta = (pi/6)/(Nposition-1);
torque_Arkkio = zeros(1,Nposition);
torque_MST = Nposition;
Wcoenergy = Nposition;

x = tic;
for i = 1:Nposition    
    [Wcoenergy(i),torque_MST(i), torque_Arkkio(i)] = runMSA(rotorPosition(i));
end

fprintf('SWEEP %.2f s for %d positions, Arkkio T range %.3f..%.3f\n', toc(x), Nposition, min(torque_Arkkio), max(torque_Arkkio)); return;

% torque calculated previously by ANSYS Maxwell
fid = fopen('C:emdlab-win64examplesswitched-reluctance-machinesrm-te-maxwell.tab','r');
fgetl(fid);
data = fscanf(fid,'%f');
fclose(fid);
data = reshape(data,2,[])';
te = data(:,2);

% plot torque curves
figure;
title('Static Torque Curve');
hold on; box on;
%plot(rotorPosition,te,'marker','^');
%plot(rotorPosition,torque_Arkkio,'marker','s');
%plot(rotorPosition,torque_MST,'marker','o');
%plot(rotorPosition,diff_cen(Wcoenergy,Delta_Theta),'marker','*');
xlabel('Rotor Position [deg]');
ylabel('Electric Torque [Nm]');
legend('ANSYS Maxwell', 'Arkkio', 'MST', 'Coenergy')

function [Wcoenergy, torque_MST, torque_Arkkio] = runMSA(rotorPosition)
% variables
gv_Ns = 8;
gv_Nr = 6;
gv_Dsh = 20;
gv_ISD = 74;
gv_OSD = 125;
gv_gap = 0.5;
gv_beta_r = 19.8 * pi/180;
gv_beta_s = 17.1 * pi/180;
gv_wry = 7.53;
gv_wsy = 7.7;
% mesh density function
f_mesh = @(r) interp1([gv_Dsh/2,gv_ISD/2,gv_OSD/2], [gv_wry/2,gv_gap,gv_wsy/2], r);
% generation of geometry
g = emdlab_g2d_db;
emdlab_g2d_lib_srm1(g, gv_Ns, gv_Nr, gv_Dsh, gv_ISD, gv_OSD, gv_gap, gv_beta_r, gv_beta_s, gv_wry, gv_wsy)
% mesh generation
g.setMeshLengthByRadialFunction(f_mesh);
m = g.generateMesh('mg0');
m.setPrintFlag(0);
% set mesh zone colors
m.setMeshZoneColor('Rotor',90,90,90);
m.setMeshZoneColor('Stator',90,90,90);
m.setMeshZoneColor('RotorAP',200,191,231);
m.setMeshZoneColor('sca',255,137,39);
% add materials
m.addMaterial('m530', emdlab_mlib_es_M530_50A);
m.addMaterial('copper', emdlab_mlib_copper);
% set materials
m.setMaterial('Rotor','m530');
m.setMaterial('Stator','m530');
m.setMaterial('sca','copper');
% construct full mesh
m.aux_cmxjcrj('Rotor', gv_Nr);
m.aux_cmxjcrj('Stator', gv_Ns);
m.aux_cmxjcrj('RotorAP', gv_Nr);
m.aux_cmxcr('sca', gv_Ns);
% rotate moving mesh zones
m.rotateMeshZone('Rotor', (rotorPosition-30)*pi/180);
m.rotateMeshZone('RotorAP', (rotorPosition-30)*pi/180);
% generate air gap mesh
m.aux_addCircularAirGap('ag',0,0,gv_ISD/2-gv_gap,0,0,gv_ISD/2,2)
% getting an instance of solver object
s = emdlab_solvers_ms2d_tl3_ihnl(m);
% setting physical units
s.setLengthUnit('mm');
s.setDepth(70);
% define new winding
s.defineCoil('phaseA');
s.addMeshZone2Coil('phaseA','sca11',278,1);
s.addMeshZone2Coil('phaseA','sca21',278,-1);
s.addMeshZone2Coil('phaseA','sca15',278,-1);
s.addMeshZone2Coil('phaseA','sca25',278,1);
% set winding current
s.setCoilCurrent('phaseA', 3.6);
% apply boundary conditions
s.setAzBC(m.getfbn, 0);
% solve and return results
evalc("s.solve;");

[~,Wcoenergy] = s.evalTotalEnergyCoenergy;
torque_MST = s.evalTorqueByMST3(0, 0, gv_ISD/2-gv_gap/2, gv_gap);
torque_Arkkio = s.evalTorqueByArkkio('ag', gv_gap);

end

